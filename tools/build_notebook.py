#!/usr/bin/env python3
"""Собирает mailru_to_drive.ipynb из исходников ячеек.

Ноутбук держим сгенерированным, а не рукописным: править питон в обычном
.py куда приятнее, чем экранированный JSON внутри .ipynb.

    python3 tools/build_notebook.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "mailru_to_drive.ipynb"


# ─────────────────────────────────────────────────────────────────────────────
# Ячейки
# ─────────────────────────────────────────────────────────────────────────────

MD_INTRO = r'''# Курс с Mail.ru Облака → Google Drive

Качает многотомный архив с публичной ссылки Mail.ru, распаковывает его
(в том числе запароленный) и складывает готовые файлы в твой Google Drive.

**Ничего не оседает на твоём компьютере.** Качает и распаковывает виртуалка
Google, а результат сразу уезжает в Drive.

---

### Как пользоваться

1. **Настройки** — вставь ссылку и пароль от архива.
2. Дальше выполняй ячейки сверху вниз, по одной, дожидаясь каждой.
3. Не закрывай вкладку: Colab отключает простаивающие сессии примерно
   через 90 минут.

Если связь оборвётся — просто запусти ячейку загрузки заново, она
продолжит с того места, где встала, а не с нуля.

### Сколько ждать

Около 27 ГБ. Обычно Colab тянет с Mail.ru быстрее домашнего интернета,
так что ориентир — от 30 минут до пары часов, плюс минут 15 на распаковку
и перенос в Drive.
'''


CODE_CONFIG = r'''#@title ⚙️ Настройки { display-mode: "form" }

#@markdown **Ссылка на публичную папку Mail.ru**
MAILRU_URL = "https://cloud.mail.ru/public/ea77/faVuPoSLZ"  #@param {type:"string"}

#@markdown **Пароль от архива** (лежит в `ПАРОЛЬ....pdf` внутри той же папки).
#@markdown Оставь пустым, если архив без пароля.
ARCHIVE_PASSWORD = ""  #@param {type:"string"}

#@markdown **Папка в Google Drive**, куда положить результат
DRIVE_FOLDER = "Курсы"  #@param {type:"string"}

#@markdown **Что скачивать:** только архивы (`.rar`, `.001`…) или вообще всё,
#@markdown что лежит в папке, включая pdf и превью.
WHAT_TO_GRAB = "только архивы"  #@param ["только архивы", "все файлы"]

#@markdown **Оставить архивы в Drive** после распаковки.
#@markdown Обычно не нужно — они занимают место, а всё полезное уже распаковано.
KEEP_ARCHIVES = False  #@param {type:"boolean"}

WORK_DIR = "/content/work"

print("Ссылка   :", MAILRU_URL)
print("Пароль   :", "задан" if ARCHIVE_PASSWORD else "не задан")
print("В Drive  :", DRIVE_FOLDER)
print("Качаем   :", WHAT_TO_GRAB)
'''


CODE_INSTALL = r'''#@title 📦 Шаг 1. Установка распаковщика
#@markdown Ставит `unrar` и 7-Zip. Занимает несколько секунд.

import shutil, subprocess

print("Ставлю пакеты, подожди...")
subprocess.run("apt-get -qq update", shell=True, capture_output=True)
subprocess.run(
    "apt-get -qq install -y unrar p7zip-full p7zip-rar",
    shell=True, capture_output=True,
)
subprocess.run("pip -q install requests tqdm", shell=True, capture_output=True)


def pick_tool():
    """Возвращает (вид, путь) первого найденного распаковщика."""
    for name in ("unrar",):
        p = shutil.which(name)
        if p:
            return "unrar", p
    for name in ("7zz", "7z", "7za"):
        p = shutil.which(name)
        if p:
            return "7z", p
    return None, None


KIND, TOOL = pick_tool()
if TOOL:
    print(f"\n✅ Распаковщик: {TOOL}")
else:
    print(
        "\n❌ Распаковщик не установился.\n"
        "   Попробуй выполнить вручную в новой ячейке:\n"
        "   !apt-get install -y unrar\n"
        "   и запусти эту ячейку снова."
    )
'''


CODE_MOUNT = r'''#@title 🔗 Шаг 2. Подключение Google Drive
#@markdown Colab попросит разрешение на доступ к твоему Drive — это нормально,
#@markdown иначе ему некуда положить результат. Жми «Разрешить».

import os
from pathlib import Path

DRIVE_ROOT = None
try:
    from google.colab import drive as _gdrive

    _gdrive.mount("/content/drive")
    DRIVE_ROOT = Path("/content/drive/MyDrive")
except ImportError:
    # Ноутбук запущен не в Colab (например, локально в Jupyter) —
    # тогда просто складываем результат рядом.
    DRIVE_ROOT = Path(os.path.expanduser("~")) / "obwaya-out"
    print("Это не Colab. Результат положу в:", DRIVE_ROOT)

DEST = DRIVE_ROOT / DRIVE_FOLDER
DEST.mkdir(parents=True, exist_ok=True)

free_gb = shutil.disk_usage("/content").free / 2**30
print(f"\n✅ Готово. Результат поедет в: {DEST}")
print(f"   Свободно на виртуалке: {free_gb:.0f} ГБ")
if free_gb < 60:
    print("   ⚠️  Меньше 60 ГБ — для архива на 27 ГБ может не хватить.")
'''


CODE_CORE = r'''#@title 🧠 Шаг 3. Загрузка служебного кода
#@markdown Ничего не делает, просто объявляет функции. Выполни и иди дальше.

import json, re, subprocess, sys, time, urllib.parse
from pathlib import Path

import requests
from tqdm.auto import tqdm

API = "https://cloud.mail.ru/api/v2"
HDRS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://cloud.mail.ru/",
    "Accept": "*/*",
}

ARCHIVE_RE = re.compile(r"\.(rar|r\d{2,3}|zip|z\d{2}|7z|\d{3})$", re.I)


def human(n):
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024 or unit == "ТБ":
            return f"{n:.1f} {unit}" if unit != "Б" else f"{n:.0f} Б"
        n /= 1024


def weblink_id(s):
    """Из https://cloud.mail.ru/public/ea77/faVuPoSLZ делает ea77/faVuPoSLZ."""
    s = s.strip()
    m = re.search(r"/public/([^?#\s]+)", s)
    return (m.group(1) if m else s).strip("/")


def api_get(method, **params):
    r = requests.get(f"{API}/{method}", params=params, headers=HDRS, timeout=30)
    try:
        payload = r.json()
    except ValueError:
        raise RuntimeError(
            f"{method}: HTTP {r.status_code}, ответ не похож на JSON:\n{r.text[:300]}"
        )
    if payload.get("status") != 200:
        raise RuntimeError(
            f"{method}: Mail.ru ответил status={payload.get('status')}\n"
            f"{json.dumps(payload, ensure_ascii=False)[:400]}"
        )
    return payload["body"]


def _folder_page(target):
    """Все элементы папки, с проходом по страницам."""
    items, offset, limit = [], 0, 500
    while True:
        body = api_get("folder", weblink=target, limit=limit, offset=offset)
        if body.get("type") == "file":
            return body, None
        chunk = body.get("list") or []
        items += chunk
        if len(chunk) < limit:
            return body, items
        offset += limit


def list_public(wl, prefix=""):
    """Рекурсивно собирает плоский список файлов публичной ссылки."""
    target = wl if not prefix else f"{wl}/{prefix.rstrip('/')}"
    body, items = _folder_page(target)

    if items is None:  # ссылка ведёт на одиночный файл
        name = body.get("name", "file")
        return [{"path": prefix or name, "name": name, "size": int(body.get("size", 0))}]

    out = []
    for it in items:
        name = it.get("name", "")
        rel = f"{prefix}{name}"
        if (it.get("type") or it.get("kind")) == "folder":
            out += list_public(wl, rel + "/")
        else:
            out.append({"path": rel, "name": name, "size": int(it.get("size", 0))})
    return out


def get_shard():
    """Адрес сервера раздачи. Mail.ru отдаёт его отдельным запросом."""
    body = api_get("dispatcher")
    for key in ("weblink_get", "get"):
        arr = body.get(key) or []
        if arr and arr[0].get("url"):
            return arr[0]["url"].rstrip("/")
    raise RuntimeError(
        "Не нашёл адрес сервера раздачи в ответе dispatcher:\n"
        f"{json.dumps(body, ensure_ascii=False)[:400]}"
    )


def build_url(shard, wl, relpath):
    return f"{shard}/{wl}/{urllib.parse.quote(relpath)}"


def download(url, dest: Path, expected=None, retries=15):
    """Качает файл с докачкой после обрыва."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    attempt = 0

    while True:
        have = dest.stat().st_size if dest.exists() else 0
        if expected and have >= expected:
            return  # уже скачан

        headers = dict(HDRS)
        mode = "wb"
        if have:
            headers["Range"] = f"bytes={have}-"
            mode = "ab"

        try:
            with requests.get(
                url, headers=headers, stream=True, timeout=(30, 120)
            ) as r:
                if have and r.status_code == 200:
                    # сервер проигнорировал Range — качаем сначала
                    have, mode = 0, "wb"
                elif r.status_code not in (200, 206):
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

                length = int(r.headers.get("Content-Length") or 0)
                total = expected or (have + length) or None

                with open(dest, mode) as f, tqdm(
                    total=total,
                    initial=have,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=dest.name[:38],
                    leave=True,
                ) as bar:
                    for chunk in r.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            bar.update(len(chunk))

            got = dest.stat().st_size
            if expected and got < expected:
                raise RuntimeError(f"недокачано: {got} из {expected}")
            return

        except Exception as exc:
            attempt += 1
            if attempt > retries:
                raise
            wait = min(60, 2 ** min(attempt, 6))
            print(f"  ⚠️  обрыв ({exc}); повтор #{attempt} через {wait} с")
            time.sleep(wait)


def find_first_volume(files):
    """Первый том многотомника — с него запускается распаковка."""
    rars = [f for f in files if ARCHIVE_RE.search(f.name)]
    if not rars:
        return None
    for f in rars:  # Name.part1.rar / Name.part01.rar
        if re.search(r"\.part0*1\.rar$", f.name, re.I):
            return f
    for f in rars:  # старый стиль: Name.rar + Name.r00 + Name.r01
        if f.suffix.lower() == ".rar" and not re.search(
            r"\.part\d+\.rar$", f.name, re.I
        ):
            return f
    for f in sorted(rars):  # Name.rar.001
        if re.search(r"\.001$", f.name):
            return f
    return sorted(rars)[0]


def extract(first: Path, outdir: Path, password=""):
    """Распаковывает архив, показывая прогресс. Бросает исключение при ошибке."""
    outdir.mkdir(parents=True, exist_ok=True)

    if KIND == "unrar":
        cmd = [TOOL, "x", "-y", "-o+", f"-p{password or '-'}",
               str(first), str(outdir) + "/"]
    else:
        cmd = [TOOL, "x", "-y", "-bsp1", "-bse1", f"-o{outdir}",
               f"-p{password}", str(first)]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0
    )

    bar = tqdm(total=100, desc="Распаковка", unit="%", leave=True)
    seen, tail = 0, []
    buf = b""

    while True:
        byte = proc.stdout.read(1)
        if not byte:
            break
        if byte in (b"\r", b"\n"):
            line = buf.decode("utf-8", "replace").strip()
            buf = b""
            if not line:
                continue
            tail.append(line)
            del tail[:-25]
            m = re.findall(r"(\d{1,3})%", line)
            if m:
                pct = min(100, int(m[-1]))
                if pct > seen:
                    bar.update(pct - seen)
                    seen = pct
        else:
            buf += byte

    proc.wait()
    bar.update(100 - seen)
    bar.close()

    if proc.returncode != 0:
        joined = "\n".join(tail)
        hint = ""
        if re.search(r"password|парол", joined, re.I):
            hint = "\n\n👉 Похоже на неверный пароль. Проверь его в PDF-файле."
        elif re.search(r"cannot find volume|не найден том", joined, re.I):
            hint = "\n\n👉 Не хватает какого-то тома. Скачай недостающие части."
        raise RuntimeError(
            f"Распаковщик вернул ошибку (код {proc.returncode}):\n{joined}{hint}"
        )


def copy_tree(src: Path, dst: Path):
    """Переносит дерево файлов в Drive, показывая общий прогресс в байтах."""
    files = [p for p in src.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    dst.mkdir(parents=True, exist_ok=True)

    with tqdm(
        total=total, unit="B", unit_scale=True, unit_divisor=1024, desc="В Drive"
    ) as bar:
        for p in files:
            target = dst / p.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "rb") as fin, open(target, "wb") as fout:
                while True:
                    chunk = fin.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    fout.write(chunk)
                    bar.update(len(chunk))
    return len(files), total


print("✅ Код загружен.")
'''


CODE_LIST = r'''#@title 📋 Шаг 4. Что лежит по ссылке
#@markdown Спрашивает у Mail.ru список файлов и показывает, что будет скачано.

WL = weblink_id(MAILRU_URL)
print(f"Публичная ссылка: {WL}\nСпрашиваю список файлов...\n")

ALL_FILES = list_public(WL)

if WHAT_TO_GRAB == "только архивы":
    PICKED = [f for f in ALL_FILES if ARCHIVE_RE.search(f["name"])]
else:
    PICKED = list(ALL_FILES)

picked_paths = {f["path"] for f in PICKED}
total = sum(f["size"] for f in PICKED)

print(f"Всего в папке: {len(ALL_FILES)} файлов\n")
for f in sorted(ALL_FILES, key=lambda x: x["path"]):
    mark = "✅" if f["path"] in picked_paths else "  "
    print(f"{mark} {human(f['size']):>10}  {f['path']}")

print(f"\nК загрузке: {len(PICKED)} файлов, {human(total)}")

if not PICKED:
    print("\n❌ Нечего качать. Поменяй режим в настройках на «все файлы».")
else:
    need = total * 2 / 2**30
    free = shutil.disk_usage("/content").free / 2**30
    print(f"Нужно места: ~{need:.0f} ГБ (архив + распакованное), свободно {free:.0f} ГБ")
    if need > free:
        print("⚠️  Может не хватить места. Архивы удалю сразу после распаковки.")
'''


CODE_DOWNLOAD = r'''#@title ⬇️ Шаг 5. Скачивание
#@markdown Самая долгая часть. Если оборвётся — просто запусти ячейку заново,
#@markdown она продолжит с места обрыва.

SHARD = get_shard()
RAW = Path(WORK_DIR) / "raw"
RAW.mkdir(parents=True, exist_ok=True)

print(f"Сервер раздачи: {SHARD}\n")
started = time.time()

for i, f in enumerate(sorted(PICKED, key=lambda x: x["path"]), 1):
    dest = RAW / f["path"]
    if dest.exists() and dest.stat().st_size == f["size"]:
        print(f"[{i}/{len(PICKED)}] {f['path']} — уже скачан, пропускаю")
        continue
    print(f"[{i}/{len(PICKED)}] {f['path']}")
    download(build_url(SHARD, WL, f["path"]), dest, expected=f["size"])

elapsed = time.time() - started
got = sum(p.stat().st_size for p in RAW.rglob("*") if p.is_file())
speed = got / elapsed if elapsed else 0
print(f"\n✅ Скачано {human(got)} за {elapsed/60:.0f} мин ({human(speed)}/с)")
'''


CODE_EXTRACT = r'''#@title 📂 Шаг 6. Распаковка
#@markdown Использует пароль из настроек. Архивы удаляются сразу после
#@markdown успешной распаковки, чтобы освободить место.

OUT = Path(WORK_DIR) / "out"
archives = sorted(p for p in RAW.rglob("*") if p.is_file() and ARCHIVE_RE.search(p.name))
first = find_first_volume(archives)

if not first:
    print("❌ Архивов не найдено — распаковывать нечего.")
else:
    print(f"Первый том: {first.name}")
    print(f"Всего томов: {len(archives)}\n")
    extract(first, OUT, ARCHIVE_PASSWORD)

    files = [p for p in OUT.rglob("*") if p.is_file()]
    print(f"\n✅ Распаковано: {len(files)} файлов, "
          f"{human(sum(p.stat().st_size for p in files))}\n")

    for p in sorted(files)[:40]:
        print(f"   {human(p.stat().st_size):>10}  {p.relative_to(OUT)}")
    if len(files) > 40:
        print(f"   ... и ещё {len(files) - 40}")

    if not KEEP_ARCHIVES:
        freed = sum(p.stat().st_size for p in archives)
        for p in archives:
            p.unlink()
        print(f"\n🧹 Архивы удалены, освободилось {human(freed)}")
'''


CODE_TO_DRIVE = r'''#@title 🚀 Шаг 7. Перенос в Google Drive
#@markdown Складывает распакованное (и всё остальное, что качали) в Drive.

name = Path(MAILRU_URL.rstrip("/")).name
title = (ALL_FILES[0]["path"].split("/")[0] if "/" in ALL_FILES[0]["path"] else "") or name
target = DEST / title

moved_files = moved_bytes = 0

if OUT.exists() and any(OUT.rglob("*")):
    n, b = copy_tree(OUT, target)
    moved_files += n
    moved_bytes += b

# Всё, что качали, но не распаковывали: pdf с паролем, txt, превью.
leftovers = [
    p for p in RAW.rglob("*") if p.is_file() and not ARCHIVE_RE.search(p.name)
]
if leftovers or (KEEP_ARCHIVES and any(RAW.rglob("*"))):
    n, b = copy_tree(RAW, target / "_исходники")
    moved_files += n
    moved_bytes += b

print(f"\n✅ Готово: {moved_files} файлов, {human(moved_bytes)}")
print(f"   Лежит здесь: {target}")
print("\nОткрывай Google Drive — папка на месте, видео играются прямо в браузере.")

shutil.rmtree(WORK_DIR, ignore_errors=True)
print("🧹 Временные файлы виртуалки подчищены.")
'''


MD_TROUBLE = r'''---

## Если что-то пошло не так

**`status=400` или `status=404` на шаге 4**
Ссылка протухла или папку закрыли. Открой её в браузере — если не
открывается и там, дело не в ноутбуке.

**Скачивание постоянно рвётся**
Это нормально для Mail.ru, загрузчик сам переподключается до 15 раз. Если
всё же остановился — просто запусти ячейку загрузки ещё раз, она продолжит
с места обрыва, заново качать не будет.

**«Похоже на неверный пароль»**
Пароль лежит в `ПАРОЛЬ....pdf` в той же папке Mail.ru. Скачай и открой его.
Осторожнее с пробелами по краям при копировании — они считаются частью
пароля.

**«Не хватает какого-то тома»**
Один из партов не докачался. Запусти шаг 5 заново, он проверит размеры
и дотянет недостающее.

**Кончилось место на виртуалке**
Поставь в настройках `WHAT_TO_GRAB = "только архивы"` и убедись, что
`KEEP_ARCHIVES` выключен. Тогда пик по диску — примерно два размера архива.

**Colab отключился на середине**
Подключись заново и выполни ячейки сверху вниз. Всё, что успело скачаться,
пропадёт вместе с виртуалкой — но если распаковка уже дошла до Drive, оно
там и осталось.

**Видео не играется в Drive**
Значит, внутри не `mp4`, а что-то вроде `mkv` — браузерный плеер Drive
такое не умеет. Напиши мне, какое расширение у файлов, и решим, что делать
дальше.
'''


# ─────────────────────────────────────────────────────────────────────────────
# Сборка
# ─────────────────────────────────────────────────────────────────────────────

def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)}


def code(text):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"cellView": "form"},
        "outputs": [],
        "source": text.splitlines(True),
    }


def main():
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {"provenance": [], "toc_visible": True},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
        },
        "cells": [
            md(MD_INTRO),
            code(CODE_CONFIG),
            code(CODE_INSTALL),
            code(CODE_MOUNT),
            code(CODE_CORE),
            code(CODE_LIST),
            code(CODE_DOWNLOAD),
            code(CODE_EXTRACT),
            code(CODE_TO_DRIVE),
            md(MD_TROUBLE),
        ],
    }

    OUT.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Записал {OUT} ({OUT.stat().st_size} байт, {len(notebook['cells'])} ячеек)")


if __name__ == "__main__":
    main()
