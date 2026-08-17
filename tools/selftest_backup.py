#!/usr/bin/env python3
"""Проверка кода блокнота переноса облака Mail.ru.

Настоящий rclone в песочнице недоступен, поэтому подставляем скрипт-заглушку
с тем же интерфейсом. Проверяется всё, что не требует живого Mail.ru: разбор
его ответов, состав команд, обработка неверного пароля и то, что пароль не
остаётся в памяти блокнота.
"""

import json
import os
import stat
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "mailru_backup_to_drive.ipynb"

PASSWORD = "секретный-пароль-от-внешних-приложений"

STUB = r"""#!/bin/sh
case "$1" in
  version) echo "rclone v1.99.0-stub"; exit 0 ;;
  obscure) echo "OBSCURED-TOKEN"; exit 0 ;;
  lsd)
    if [ -n "$STUB_FAIL_LOGIN" ]; then
      echo "Failed to create file system: authentication failed: invalid password" >&2
      exit 1
    fi
    echo "          -1 2026-01-01 00:00:00        -1 Фото"
    echo ""
    echo "          -1 2026-01-01 00:00:00        -1 Документы"
    exit 0 ;;
  about)
    echo "Total:   8 GiB"
    echo "Used:    13.4 GiB"
    exit 0 ;;
  size)
    echo "Total objects: 1 234"
    echo "Total size: 13.4 GiB (14388658176 Byte)"
    exit 0 ;;
  *) echo "stub called: $*"; exit 0 ;;
esac
"""


def cell_with(marker):
    cells = json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
    return next(
        "".join(c["source"])
        for c in cells
        if c["cell_type"] == "code" and marker in "".join(c["source"])
    )


def make_stub(tmp: Path):
    path = tmp / "rclone"
    path.write_text(STUB)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def load_core(stub, dest, source=""):
    """Выполняет ячейку входа целиком, подсунув фальшивый getpass."""
    real = sys.modules.get("getpass")
    fake = types.ModuleType("getpass")
    fake.getpass = lambda prompt="": PASSWORD
    sys.modules["getpass"] = fake
    try:
        ns = {
            "__name__": "core",
            "RCLONE": str(stub),
            "DEST": dest,
            "MAILRU_EMAIL": "test@mail.ru",
            "SOURCE": source,
            "TRANSFERS": 4,
            "DRY_RUN": True,
        }
        exec(compile(cell_with("def copy_args"), "core-cell", "exec"), ns)
        return ns
    finally:
        if real is not None:
            sys.modules["getpass"] = real
        else:
            sys.modules.pop("getpass", None)


def main(check):
    ok = True

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stub = make_stub(tmp)
        dest = tmp / "drive"
        dest.mkdir()

        # ── вход проходит, окружение настроено ───────────────────────────
        ns = load_core(stub, dest)

        ok &= check(
            "remote настроен через переменные окружения",
            os.environ.get("RCLONE_CONFIG_MAILRU_TYPE") == "mailru"
            and os.environ.get("RCLONE_CONFIG_MAILRU_USER") == "test@mail.ru"
            and os.environ.get("RCLONE_CONFIG_MAILRU_PASS") == "OBSCURED-TOKEN",
        )

        # Пароль обязан исчезнуть: в сохранённом блокноте его быть не должно.
        leaked = [k for k, v in ns.items() if isinstance(v, str) and PASSWORD in v]
        ok &= check(
            "пароль не остался в памяти блокнота",
            not leaked and PASSWORD not in os.environ.get("RCLONE_CONFIG_MAILRU_PASS", ""),
            f"нашёлся в {leaked}" if leaked else "",
        )
        ok &= check(
            "в тексте блокнота пароля нет",
            PASSWORD not in NOTEBOOK.read_text(encoding="utf-8"),
        )

        # ── разбор вывода rclone ────────────────────────────────────────
        rc, lines = ns["run_rclone"](["lsd", "mailru:"], echo=False)
        ok &= check(
            "run_rclone: код возврата и строки без пустых",
            rc == 0 and len(lines) == 2 and all(lines),
            f"rc={rc}, строк={len(lines)}",
        )

        human = ns["human"]
        ok &= check("human(14388658176)", human(14388658176).startswith("13.4"), human(14388658176))

        # Ровно те регулярки, которыми Шаг 4 достаёт объём из вывода rclone.
        import re

        out = "Total objects: 1 234\nTotal size: 13.4 GiB (14388658176 Byte)"
        files = int(re.sub(r"\D", "", re.search(r"Total objects:\s*([\d\s]+)", out).group(1)))
        size = int(re.search(r"Total size:.*?\((\d+) Byte", out).group(1))
        ok &= check(
            "разбор объёма облака",
            files == 1234 and size == 14388658176,
            f"{files} файлов, {human(size)}",
        )

        # ── состав команды копирования ──────────────────────────────────
        args = ns["copy_args"]("mailru:Фото", dest, 6, dry_run=True)
        ok &= check(
            "copy_args: пробный прогон помечен --dry-run",
            "--dry-run" in args and args[:2] == ["copy", "mailru:Фото"],
        )
        ok &= check(
            "copy_args: потоки и повторы на месте",
            args[args.index("--transfers") + 1] == "6" and "--retries" in args,
        )
        real_args = ns["copy_args"]("mailru:", dest, 4, dry_run=False)
        ok &= check(
            "copy_args: в боевом режиме --dry-run нет",
            "--dry-run" not in real_args,
        )

        ok &= check("src_remote(): всё облако", ns["src_remote"]() == "mailru:", ns["src_remote"]())

        ns2 = load_core(stub, dest, source="/Фото/")
        ok &= check(
            "src_remote(): отдельная папка, лишние слэши убраны",
            ns2["src_remote"]() == "mailru:Фото",
            ns2["src_remote"](),
        )

        # ── подсказки по ошибкам ────────────────────────────────────────
        hint = ns["login_hint"]
        ok &= check(
            "неверный пароль → совет про пароль для внешних приложений",
            "внешних приложений" in hint("authentication failed: invalid password"),
        )
        ok &= check(
            "переполнение → совет снять ограничение",
            "ограничение" in hint("error: user overquota, access restricted"),
        )
        ok &= check("непонятная ошибка → без выдумок", hint("connection reset by peer") == "")

        # ── неверный пароль валит вход с внятным текстом ─────────────────
        os.environ["STUB_FAIL_LOGIN"] = "1"
        try:
            load_core(stub, dest)
            ok &= check("неверный пароль останавливает работу", False, "вход прошёл!")
        except RuntimeError as exc:
            ok &= check(
                "неверный пароль останавливает работу",
                "внешних приложений" in str(exc),
                str(exc).splitlines()[0][:60],
            )
        finally:
            os.environ.pop("STUB_FAIL_LOGIN", None)

        for key in list(os.environ):
            if key.startswith("RCLONE_CONFIG_MAILRU"):
                del os.environ[key]

    return ok
