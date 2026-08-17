#!/usr/bin/env python3
"""Проверка кода ноутбука на настоящих многотомных архивах.

Из ноутбука вытаскивается ячейка с функциями и выполняется как есть — так
тестируется ровно тот код, который увидит пользователь, а не его копия.

    python3 tools/selftest.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "mailru_to_drive.ipynb"

PASSWORD = "пароль от курса 2026"  # с пробелами и кириллицей — как в жизни


def load_core():
    """Выполняет ячейку с функциями и возвращает её пространство имён."""
    cells = json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
    core = next(
        "".join(c["source"])
        for c in cells
        if c["cell_type"] == "code" and "def find_first_volume" in "".join(c["source"])
    )

    tool = shutil.which("7zz") or shutil.which("7z") or shutil.which("7za")
    ns = {"__name__": "core", "KIND": "7z", "TOOL": tool}
    exec(compile(core, "core-cell", "exec"), ns)
    return ns


def make_archive(workdir: Path, payload: Path):
    """Собирает многотомный запароленный 7z из подготовленных файлов."""
    out = workdir / "course.7z"
    subprocess.run(
        [shutil.which("7z") or "7z", "a", "-v4m", f"-p{PASSWORD}", "-mhe=on",
         str(out), str(payload) + "/."],
        check=True, capture_output=True,
    )
    return sorted(workdir.glob("course.7z.*"))


def make_payload(root: Path):
    """Дерево, похожее на курс: вложенные папки, кириллица, крупные файлы."""
    lessons = root / "Модуль 1"
    lessons.mkdir(parents=True)
    (root / "Модуль 2").mkdir()

    made = {}
    for name, size in [
        ("Модуль 1/урок 01 - введение.mp4", 5 << 20),
        ("Модуль 1/урок 02 - практика.mp4", 6 << 20),
        ("Модуль 2/урок 10 - финал.mp4", 4 << 20),
        ("конспект.pdf", 1 << 20),
    ]:
        p = root / name
        # Случайные байты: видео не сжимается, и архив честно бьётся на тома.
        p.write_bytes(os.urandom(size))
        made[name] = p.stat().st_size
    return made


class FlakyHandler(BaseHTTPRequestHandler):
    """Сервер, который честно понимает Range, но первые N раз рвёт связь."""

    blob = b""
    fail_times = 2
    attempts = 0
    ranges_seen = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        cls = type(self)
        cls.attempts += 1
        total = len(cls.blob)

        start = 0
        rng = self.headers.get("Range")
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            cls.ranges_seen.append(start)

        body = cls.blob[start:]
        self.send_response(206 if rng else 200)
        self.send_header("Content-Length", str(len(body)))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{total - 1}/{total}")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

        if cls.attempts <= cls.fail_times:
            # Отдаём половину и обрываемся, как это делает Mail.ru под нагрузкой.
            self.wfile.write(body[: len(body) // 2])
            self.wfile.flush()
            self.close_connection = True
            return

        self.wfile.write(body)


def test_resume(ns, ok):
    """Обрыв на середине не должен приводить к перекачке с нуля."""
    payload = os.urandom(3 << 20)
    FlakyHandler.blob = payload
    FlakyHandler.attempts = 0
    FlakyHandler.ranges_seen = []

    srv = ThreadingHTTPServer(("127.0.0.1", 0), FlakyHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/course.part1.rar"

    # Не ждём реальные паузы между повторами.
    ns["time"] = SimpleNamespace(time=time.time, sleep=lambda _s: None)

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "course.part1.rar"
        ns["download"](url, dest, expected=len(payload))

        ok &= check(
            "докачка: файл собран верно",
            dest.read_bytes() == payload,
            f"{dest.stat().st_size} из {len(payload)} байт",
        )
        ok &= check(
            "докачка: было несколько попыток",
            FlakyHandler.attempts > FlakyHandler.fail_times,
            f"{FlakyHandler.attempts} попыток",
        )
        ok &= check(
            "докачка: продолжали с места обрыва, а не с нуля",
            FlakyHandler.ranges_seen and all(s > 0 for s in FlakyHandler.ranges_seen),
            f"Range со смещений {FlakyHandler.ranges_seen}",
        )

    # Повторный вызов на готовом файле не должен лезть в сеть.
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "done.rar"
        dest.write_bytes(payload)
        before = FlakyHandler.attempts
        ns["download"](url, dest, expected=len(payload))
        ok &= check("скачанный файл не качается заново", FlakyHandler.attempts == before)

    srv.shutdown()
    return ok


def check(label, condition, detail=""):
    mark = "✅" if condition else "❌"
    print(f"{mark} {label}" + (f" — {detail}" if detail else ""))
    return bool(condition)


def main():
    ns = load_core()
    ok = True

    # ── чистые функции ───────────────────────────────────────────────────
    weblink_id = ns["weblink_id"]
    for raw, want in [
        ("https://cloud.mail.ru/public/ea77/faVuPoSLZ", "ea77/faVuPoSLZ"),
        ("https://cloud.mail.ru/public/ea77/faVuPoSLZ/", "ea77/faVuPoSLZ"),
        ("https://cloud.mail.ru/public/ea77/faVuPoSLZ?weblink=1", "ea77/faVuPoSLZ"),
        ("ea77/faVuPoSLZ", "ea77/faVuPoSLZ"),
    ]:
        ok &= check(f"weblink_id({raw!r})", weblink_id(raw) == want, weblink_id(raw))

    find_first = ns["find_first_volume"]
    cases = [
        (["c.part3.rar", "c.part1.rar", "c.part2.rar"], "c.part1.rar"),
        (["c.part10.rar", "c.part01.rar", "c.part02.rar"], "c.part01.rar"),
        (["c.r01", "c.rar", "c.r00"], "c.rar"),
        (["c.rar.002", "c.rar.001"], "c.rar.001"),
    ]
    for names, want in cases:
        got = find_first([Path(n) for n in names])
        ok &= check(f"первый том из {names}", got and got.name == want, str(got))

    human = ns["human"]
    ok &= check("human(27.6 ГБ)", human(29648622387).startswith("27.6"), human(29648622387))

    safe_name = ns["safe_name"]
    ok &= check(
        "имя папки чистится от слэшей",
        "/" not in safe_name("[SuperSliv.biz] Курс / часть 1")
        and safe_name("  курс.  ") == "курс",
        safe_name("[SuperSliv.biz] Курс / часть 1"),
    )

    nd = ns["need"]
    try:
        nd("weblink_id", "human")
        ok &= check("need(): не мешает, когда всё на месте", True)
    except RuntimeError as exc:
        ok &= check("need(): не мешает, когда всё на месте", False, str(exc))
    try:
        nd("MAILRU_URL")
        ok &= check("need(): ловит пропущенный шаг", False, "не заметил пропуска")
    except RuntimeError as exc:
        ok &= check(
            "need(): ловит пропущенный шаг",
            "Шаг 0" in str(exc) and "MAILRU_URL" in str(exc),
            str(exc).splitlines()[0][:60],
        )

    archive_re = ns["ARCHIVE_RE"]
    ok &= check(
        "распознаёт архивы, не трогает видео",
        all(archive_re.search(n) for n in ["a.rar", "a.r00", "a.7z.001", "a.zip"])
        and not any(archive_re.search(n) for n in ["урок.mp4", "ПАРОЛЬ.pdf", "readme.txt"]),
    )

    # ── докачка после обрыва ─────────────────────────────────────────────
    ok = test_resume(ns, ok)

    # ── настоящая распаковка ─────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        payload = tmp / "src"
        payload.mkdir()
        expected = make_payload(payload)

        volumes = make_archive(tmp, payload)
        ok &= check("собран многотомник", len(volumes) > 1, f"{len(volumes)} томов")

        first = find_first([*volumes])
        ok &= check("найден первый том", first and first.name.endswith(".001"), str(first))

        # неверный пароль обязан падать, а не молча выдавать мусор
        try:
            ns["extract"](first, tmp / "bad", "не тот пароль")
            ok &= check("неверный пароль отвергнут", False, "распаковалось!")
        except RuntimeError as exc:
            ok &= check("неверный пароль отвергнут", "парол" in str(exc).lower(),
                        str(exc).splitlines()[-1][:70])

        out = tmp / "out"
        ns["extract"](first, out, PASSWORD)

        for name, size in expected.items():
            got = out / name
            ok &= check(
                f"распакован {name}",
                got.is_file() and got.stat().st_size == size,
                f"{got.stat().st_size if got.is_file() else 'нет файла'} / {size}",
            )

        # перенос «в Drive»
        drive = tmp / "drive"
        n, total = ns["copy_tree"](out, drive)
        ok &= check(
            "перенос в Drive",
            n == len(expected) and total == sum(expected.values()),
            f"{n} файлов, {human(total)}",
        )
        ok &= check(
            "структура папок сохранена",
            (drive / "Модуль 1/урок 01 - введение.mp4").is_file(),
        )

    print("\n── блокнот переноса облака ─────────────────────────────────")
    import selftest_backup

    ok &= selftest_backup.main(check)

    print("\n── очиститель Mail.ru ──────────────────────────────────────")
    rc = subprocess.run(["sh", str(ROOT / "tools" / "selftest_cleanup.sh")]).returncode
    ok &= check("тесты очистителя", rc == 0)

    print("\n" + ("ВСЁ ЗЕЛЁНОЕ" if ok else "ЕСТЬ ПАДЕНИЯ"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
