#!/usr/bin/env python3
"""Собирает mailru_backup_to_drive.ipynb — перенос своего облака Mail.ru в Drive.

    python3 tools/build_backup.py
"""

from pathlib import Path

from nbbuild import code, md, write

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "mailru_backup_to_drive.ipynb"


MD_INTRO = r'''# Моё облако Mail.ru → Google Drive

Переливает содержимое твоего Mail.ru Облака в Google Drive. Файлы идут
**потоком через виртуалку Google** — на твоём компьютере не оседает ничего,
и качать-заливать руками не нужно.

Работу делает [rclone](https://rclone.org/) — стандартный инструмент для
перекачки между облаками. Своего клиента к Mail.ru не пишем: у них капча и
двухфакторка, а rclone это уже умеет.

---

### ⚠️ Что сделать до запуска

**1. Снять ограничение доступа.** Если Mail.ru пишет «Доступ к файлам
ограничен» из-за переполнения — открой их приложение или сайт и нажми
**«Снять ограничение временно»**. Пока ограничение висит, rclone файлы не
увидит.

**2. Создать пароль для внешних приложений.** Обычный пароль от почты не
подойдёт — Mail.ru не пускает по нему сторонние программы. Нужен отдельный:

- Зайди в настройки почты Mail.ru → **Безопасность**
- Раздел **«Пароли для внешних приложений»** → создать новый
- Скопируй его — вводить будешь на Шаге 3

Этот пароль даёт доступ только к файлам и почте, и его можно отозвать в
любой момент, не меняя основной пароль.

---

### Про безопасность

Пароль **не хранится в блокноте.** Он спрашивается при каждом запуске
отдельным полем и живёт только в памяти виртуалки, которая потом
уничтожается. Поэтому его нет ни в форме настроек, ни в сохранённом файле
блокнота у тебя в Drive.

### Ничего не удаляется

Блокнот только **копирует**. Из Mail.ru не удаляется ни один файл — даже
после успешного переноса. Освобождать там место будешь сам, руками, когда
своими глазами убедишься, что всё на месте. Так надёжнее: автоматическое
удаление по чужому коду — плохая идея, когда речь про единственную копию
твоих фотографий.
'''


CODE_CONFIG = r'''#@title ⚙️ Шаг 0. Настройки — запусти эту ячейку первой { display-mode: "form" }

#@markdown **Твой адрес на Mail.ru**
MAILRU_EMAIL = ""  #@param {type:"string"}

#@markdown **Что копировать.** Пусто — всё облако целиком. Или укажи папку,
#@markdown например `Фото` или `Документы/Сканы`.
SOURCE = ""  #@param {type:"string"}

#@markdown **Куда в Google Drive** положить
DRIVE_FOLDER = "Из Mail.ru Облака"  #@param {type:"string"}

#@markdown **Сколько файлов качать одновременно.** Больше — быстрее, но
#@markdown Mail.ru может начать придушивать. 4 — хороший компромисс.
TRANSFERS = 4  #@param {type:"slider", min:1, max:8, step:1}

#@markdown **Сначала прогон без копирования** — просто покажет, что и куда
#@markdown поедет. Настоятельно советую первый раз оставить включённым.
DRY_RUN = True  #@param {type:"boolean"}

print("Аккаунт  :", MAILRU_EMAIL or "❌ не указан!")
print("Копируем :", SOURCE or "всё облако")
print("В Drive  :", DRIVE_FOLDER)
print("Потоков  :", TRANSFERS)
print("Режим    :", "проба без копирования" if DRY_RUN else "🚀 копируем по-настоящему")

if not MAILRU_EMAIL:
    raise RuntimeError("Вставь свой адрес на Mail.ru в поле выше и запусти ячейку снова.")
'''


CODE_INSTALL = r'''#@title 📦 Шаг 1. Установка rclone
#@markdown Качает свежий rclone с официального сайта. Несколько секунд.

import shutil, subprocess

if "MAILRU_EMAIL" not in globals():
    raise RuntimeError(
        "Не выполнена самая первая ячейка «⚙️ Шаг 0. Настройки».\n"
        "Прокрути наверх, заполни поля, запусти её кнопкой ▶ — и возвращайся сюда."
    )

RCLONE = shutil.which("rclone")

if not RCLONE:
    print("Ставлю rclone...")
    subprocess.run(
        "cd /tmp && curl -sfO https://downloads.rclone.org/rclone-current-linux-amd64.zip "
        "&& unzip -oq rclone-current-linux-amd64.zip "
        "&& cp rclone-*-linux-amd64/rclone /usr/local/bin/rclone "
        "&& chmod +x /usr/local/bin/rclone",
        shell=True, capture_output=True,
    )
    RCLONE = shutil.which("rclone")

if not RCLONE:
    raise RuntimeError(
        "rclone не установился. Попробуй в новой ячейке:\n"
        "  !apt-get install -y rclone\n"
        "и запусти эту ячейку снова."
    )

version = subprocess.run([RCLONE, "version"], capture_output=True, text=True).stdout
print(f"✅ {version.splitlines()[0]}")
print(f"   {RCLONE}")
'''


CODE_MOUNT = r'''#@title 🔗 Шаг 2. Подключение Google Drive
#@markdown Colab попросит доступ к твоему Drive — жми «Разрешить».

import os
from pathlib import Path

DRIVE_ROOT = None
try:
    from google.colab import drive as _gdrive

    _gdrive.mount("/content/drive")
    DRIVE_ROOT = Path("/content/drive/MyDrive")
except ImportError:
    DRIVE_ROOT = Path(os.path.expanduser("~")) / "obwaya-out"
    print("Это не Colab. Копировать буду в:", DRIVE_ROOT)

DEST = DRIVE_ROOT / DRIVE_FOLDER
DEST.mkdir(parents=True, exist_ok=True)

print(f"\n✅ Файлы поедут в: {DEST}")
'''


CODE_CORE = r'''#@title 🧠 Шаг 3. Вход в Mail.ru
#@markdown Спросит **пароль для внешних приложений** (не обычный пароль от
#@markdown почты — см. вступление наверху). Он нигде не сохраняется: живёт
#@markdown только в памяти виртуалки и спрашивается заново при каждом запуске.

import getpass, os, re, subprocess, time

if "RCLONE" not in globals() or "DEST" not in globals():
    raise RuntimeError("Сначала выполни Шаги 1 и 2.")


def human(n):
    n = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024 or unit == "ТБ":
            return f"{n:.1f} {unit}"
        n /= 1024


def run_rclone(args, echo=True, keep=400):
    """Запускает rclone, показывая вывод построчно. Возвращает (код, строки)."""
    proc = subprocess.Popen(
        [RCLONE] + args,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, errors="replace",
    )
    lines = []
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        lines.append(line)
        del lines[:-keep]
        if echo:
            print(line, flush=True)
    proc.wait()
    return proc.returncode, lines


def src_remote():
    """Адрес источника для rclone: mailru: или mailru:Папка."""
    return "mailru:" + SOURCE.strip().strip("/")


def copy_args(source, dest, transfers, dry_run):
    """Аргументы для rclone copy. Вынесено отдельно, чтобы можно было проверить."""
    args = [
        "copy", source, str(dest),
        "--transfers", str(transfers),
        "--checkers", "8",
        "--retries", "5",
        "--low-level-retries", "20",
        "--stats", "15s",
        "--stats-one-line",
        "--verbose",
    ]
    if dry_run:
        args.append("--dry-run")
    return args


# Пароль спрашиваем в рантайме и кладём только в переменные окружения:
# так rclone его увидит, а сохранённый блокнот — нет.
_pw = getpass.getpass(f"Пароль для внешних приложений ({MAILRU_EMAIL}): ")
if not _pw:
    raise RuntimeError("Пароль пустой — без него Mail.ru не пустит.")

_obscured = subprocess.run(
    [RCLONE, "obscure", _pw], capture_output=True, text=True, check=True
).stdout.strip()
del _pw

os.environ["RCLONE_CONFIG_MAILRU_TYPE"] = "mailru"
os.environ["RCLONE_CONFIG_MAILRU_USER"] = MAILRU_EMAIL
os.environ["RCLONE_CONFIG_MAILRU_PASS"] = _obscured
del _obscured

def login_hint(text):
    """Переводит ругань rclone в понятный совет."""
    if re.search(r"password|auth|401|403|credential", text, re.I):
        return (
            "\n\n👉 Похоже, пароль не подошёл. Нужен именно «пароль для внешних "
            "приложений» из настроек безопасности Mail.ru, а не обычный пароль "
            "от почты. Проверь заодно, не скопировался ли пробел на конце."
        )
    if re.search(r"quota|limit|ограни|overquota", text, re.I):
        return (
            "\n\n👉 Возможно, доступ ограничен из-за переполнения. Открой "
            "приложение Mail.ru и нажми «Снять ограничение временно»."
        )
    return ""


print("\nПроверяю вход...")
# Проверяемся через lsd, а не about: about поддерживают не все бэкенды,
# и сломанная проверка выглядела бы как неверный пароль.
rc, out = run_rclone(["lsd", "mailru:", "--max-depth", "1"], echo=False)
if rc != 0:
    joined = "\n".join(out)
    raise RuntimeError(f"Войти не удалось (код {rc}):\n{joined}{login_hint(joined)}")

print("✅ Вход выполнен.")

rc_about, about = run_rclone(["about", "mailru:"], echo=False)
if rc_about == 0:
    print("\nМесто в облаке Mail.ru:")
    for line in about:
        print("  ", line)
'''


CODE_SURVEY = r'''#@title 📋 Шаг 4. Что лежит в облаке
#@markdown Считает объём и показывает папки верхнего уровня. На большом
#@markdown облаке может думать минуту-другую.

if "run_rclone" not in globals():
    raise RuntimeError("Сначала выполни Шаг 3.")

SRC = src_remote()
print(f"Источник: {SRC}\n")

print("Папки верхнего уровня:")
rc, dirs = run_rclone(["lsd", SRC], echo=False)
if rc != 0:
    raise RuntimeError("Не смог получить список папок:\n" + "\n".join(dirs))
for line in dirs:
    print("  ", line)
if not dirs:
    print("   (папок нет — возможно, файлы лежат прямо в корне)")

print("\nСчитаю объём...")
rc, size = run_rclone(["size", SRC], echo=False)
if rc != 0:
    raise RuntimeError("Не смог посчитать объём:\n" + "\n".join(size))

TOTAL_BYTES = TOTAL_FILES = 0
for line in size:
    print("  ", line)
    if m := re.search(r"Total objects:\s*([\d\s]+)", line):
        TOTAL_FILES = int(re.sub(r"\D", "", m.group(1)) or 0)
    if m := re.search(r"Total size:.*?\((\d+) Byte", line):
        TOTAL_BYTES = int(m.group(1))

if TOTAL_BYTES:
    print(f"\nК переносу: {TOTAL_FILES} файлов, {human(TOTAL_BYTES)}")
    print(f"На скорости 4 МБ/с это примерно {TOTAL_BYTES / 4e6 / 60:.0f} мин.")
'''


CODE_COPY = r'''#@title ⬇️ Шаг 5. Копирование
#@markdown Долгая часть. Каждые 15 секунд пишет строчку с прогрессом.
#@markdown
#@markdown Оборвалось? Просто запусти ячейку заново — rclone сравнит, что
#@markdown уже лежит в Drive, и докопирует только недостающее.

if "SRC" not in globals():
    raise RuntimeError("Сначала выполни Шаг 4.")

args = copy_args(SRC, DEST, TRANSFERS, DRY_RUN)

if DRY_RUN:
    print("🧪 ПРОБНЫЙ ПРОГОН — ничего не копируется, только показывается.\n"
          "   Убедился, что список правильный? Выключи DRY_RUN в Шаге 0,\n"
          "   запусти Шаг 0 заново и вернись сюда.\n")
else:
    print(f"🚀 Копирую {SRC} → {DEST}\n")

started = time.time()
rc, log = run_rclone(args)
elapsed = time.time() - started

print()
if rc != 0:
    print(f"⚠️  rclone вернул код {rc}. Последние строки лога выше.")
    print("   Часто помогает просто запустить ячейку заново — докопирует остаток.")
else:
    print(f"✅ Готово за {elapsed / 60:.0f} мин.")
    if DRY_RUN:
        print("   Это был пробный прогон. Файлы НЕ скопированы.")
'''


CODE_VERIFY = r'''#@title ✔️ Шаг 6. Проверка
#@markdown Сверяет источник с копией и говорит, всё ли доехало.
#@markdown Сравнение по размерам: Mail.ru и Google считают контрольные суммы
#@markdown по-разному, поэтому побайтово сверить не получится.

if DRY_RUN:
    print("Был пробный прогон — проверять нечего.")
else:
    print("Сверяю источник и копию...\n")
    rc, out = run_rclone(
        ["check", SRC, str(DEST), "--one-way", "--size-only"], echo=False
    )
    for line in out[-30:]:
        print("  ", line)

    missing = [l for l in out if re.search(r"ERROR|not in|differ", l, re.I)]
    print()
    if rc == 0 and not missing:
        print("✅ Всё сошлось — каждый файл из Mail.ru есть в Drive.\n")
        print("Теперь можно освобождать место в Mail.ru. Делай это сам, через")
        print("их сайт или приложение: сначала глазами убедись, что папки в")
        print("Drive действительно на месте и открываются, и только потом удаляй.")
        print("Это твоя единственная копия — блокнот к ней не прикоснётся.")
    else:
        print(f"⚠️  Есть расхождения ({len(missing)} строк). Запусти Шаг 5 ещё раз —")
        print("   он докопирует то, что не доехало, а потом вернись сюда.")
        print("   Пока не сойдётся — из Mail.ru ничего не удаляй.")
'''


MD_TROUBLE = r'''---

## Если что-то пошло не так

**«Похоже, пароль не подошёл»**
Нужен не обычный пароль от почты, а отдельный: настройки Mail.ru →
Безопасность → «Пароли для внешних приложений» → создать. Проверь заодно,
что не скопировал пробел на конце.

**«Доступ ограничен» / файлов не видно**
Открой приложение Mail.ru и нажми «Снять ограничение временно». Пока
пространство переполнено, они закрывают доступ и rclone видит пустоту.

**Копирование идёт и обрывается**
Нормально. Запусти Шаг 5 заново — rclone сверит, что уже в Drive, и
продолжит с недостающего. Перекачивать всё заново он не станет.

**Очень медленно**
Подними `TRANSFERS` в Шаге 0 до 6-8. Если после этого начнутся ошибки —
Mail.ru придушивает, верни обратно на 4 и просто дай ему время.

**Colab отключился на середине**
Подключись заново, прогони ячейки сверху вниз (пароль спросит опять) и
запусти Шаг 5. Всё уже скопированное лежит в Drive и никуда не пропало —
Drive не зависит от виртуалки.

**Хочу перенести только одну папку**
Впиши её имя в `SOURCE` в Шаге 0, например `Фото`. Регистр и пробелы
должны совпадать с тем, что показал Шаг 4.

**Не уверен, что доехало**
Шаг 6 для этого и есть. Пока он не скажет «всё сошлось» — в Mail.ru ничего
не удаляй.
'''


def main():
    write(OUT, [
        md(MD_INTRO),
        code(CODE_CONFIG),
        code(CODE_INSTALL),
        code(CODE_MOUNT),
        code(CODE_CORE),
        code(CODE_SURVEY),
        code(CODE_COPY),
        code(CODE_VERIFY),
        md(MD_TROUBLE),
    ])


if __name__ == "__main__":
    main()
