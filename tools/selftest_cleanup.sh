#!/bin/sh
# Проверка tools/mailru_cleanup.ps1 на подставном rclone.
#
# Главное, что проверяется: при неудачной сверке скрипт не должен вызывать
# delete вообще. Остальное — что -DryRun не удаляет, что отказ от
# подтверждения отменяет операцию, что успешный путь доходит до конца, и
# что без -Dest скрипт отказывает сразу, не трогая rclone.
#
# Сообщения в самом скрипте — на английском (см. комментарий там же): файл
# передаётся между машинами скачиванием, и не-ASCII текст внутри него уже
# один раз ломался в кракозябры и валил парсер PowerShell. Тесты это тоже
# проверяют — весь файл должен оставаться чистым ASCII.
#
# Без pwsh молча пропускается — на машине пользователя он есть, в песочнице
# может не быть.

set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SCRIPT="$ROOT/tools/mailru_cleanup.ps1"

if ! command -v pwsh >/dev/null 2>&1; then
    echo "⏭  pwsh не установлен — тесты очистителя пропущены"
    echo "   поставить: apt-get install -y powershell (нужен репозиторий Microsoft)"
    exit 0
fi

fails=0

check() {
    if [ "$1" = "0" ]; then
        echo "  ✅ $2"
    else
        echo "  ❌ $2"
        fails=$((fails + 1))
    fi
}

echo "Файл остаётся чистым ASCII:"
if LC_ALL=C grep -qP '[^\x00-\x7F]' "$SCRIPT" 2>/dev/null; then
    check 1 "нет не-ASCII байт (риск повторной поломки кодировки)"
else
    check 0 "нет не-ASCII байт (риск повторной поломки кодировки)"
fi

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK" || exit 1

cat > fake-rclone <<'STUB'
#!/bin/sh
echo "$@" >> "$RCLONE_LOG"
case "$1" in
  check)
    if [ -n "${STUB_CHECK_FAIL:-}" ]; then
      echo "ERROR: sizes differ"; echo "1 differences found"; exit 1
    fi
    echo "0 differences found"; exit 0 ;;
  size)
    echo "Total objects: 1731"
    echo "Total size: 13.403 GiB (14391658176 Byte)"; exit 0 ;;
  *) echo "stub: $@"; exit 0 ;;
esac
STUB
chmod +x fake-rclone

DEST="gdrive:From Mail.ru"

has()   { grep -q "$1" "$2" && echo 0 || echo 1; }
hasnt() { grep -q "$1" "$2" && echo 1 || echo 0; }

echo "Без -Dest — отказывает сразу, rclone не вызывается:"
RCLONE_LOG=$WORK/log-nodest; export RCLONE_LOG; : > "$RCLONE_LOG"
pwsh -NoProfile -File "$SCRIPT" -Rclone ./fake-rclone > out-nodest 2>&1
check "$([ $? -ne 0 ] && echo 0 || echo 1)" "вышел с ошибкой"
check "$(has 'Missing -Dest' out-nodest)" "объяснил, что не хватает -Dest"
check "$([ -s "$RCLONE_LOG" ] && echo 1 || echo 0)" "rclone не вызывался вообще"

echo "Сверка провалилась — удалять нельзя:"
RCLONE_LOG=$WORK/log-a; export RCLONE_LOG; : > "$RCLONE_LOG"
STUB_CHECK_FAIL=1 pwsh -NoProfile -File "$SCRIPT" -Rclone ./fake-rclone -Dest "$DEST" > out-a 2>&1
check "$([ $? -ne 0 ] && echo 0 || echo 1)" "вышел с ошибкой"
check "$(has 'STOP' out-a)" "объяснил, почему остановился"
check "$(hasnt 'delete' "$RCLONE_LOG")" "delete не вызывался вообще"

echo "Пробный режим:"
RCLONE_LOG=$WORK/log-b; export RCLONE_LOG; : > "$RCLONE_LOG"
unset STUB_CHECK_FAIL
pwsh -NoProfile -File "$SCRIPT" -Rclone ./fake-rclone -Dest "$DEST" -DryRun > out-b 2>&1
check "$([ $? -eq 0 ] && echo 0 || echo 1)" "завершился успешно"
check "$(has 'delete mailru: --dry-run' "$RCLONE_LOG")" "показал, что удалилось бы"
check "$(hasnt '^delete mailru: --progress' "$RCLONE_LOG")" "по-настоящему не удалял"

echo "Подтверждение не дано:"
RCLONE_LOG=$WORK/log-c; export RCLONE_LOG; : > "$RCLONE_LOG"
echo "no" | pwsh -NoProfile -File "$SCRIPT" -Rclone ./fake-rclone -Dest "$DEST" > out-c 2>&1
check "$(has 'Cancelled' out-c)" "отменил операцию"
check "$(hasnt '^delete mailru: --progress' "$RCLONE_LOG")" "ничего не удалил"

echo "Подтверждение дано:"
RCLONE_LOG=$WORK/log-d; export RCLONE_LOG; : > "$RCLONE_LOG"
echo "DELETE" | pwsh -NoProfile -File "$SCRIPT" -Rclone ./fake-rclone -Dest "$DEST" > out-d 2>&1
check "$([ $? -eq 0 ] && echo 0 || echo 1)" "завершился успешно"
check "$(has '^delete mailru: --progress' "$RCLONE_LOG")" "удалил файлы"
check "$(has 'rmdirs' "$RCLONE_LOG")" "убрал пустые папки"
check "$(has 'Trash' out-d)" "предупредил про Корзину Mail.ru"

[ "$fails" -eq 0 ] && exit 0 || exit 1
