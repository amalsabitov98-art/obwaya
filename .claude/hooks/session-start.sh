#!/bin/bash
# Готовит окружение для `python3 tools/selftest.py` в веб-сессии Claude Code.
#
# Контейнер стартует без всего этого, а тесты без него тихо деградируют:
# без 7z не проверить распаковку многотомных архивов, без pwsh пропускаются
# тесты очистителя Mail.ru. Так что ставим заранее.
#
# Скрипт идемпотентный: уже установленное пропускается.
set -euo pipefail

# Только в удалённом окружении — на своей машине пользователь ставит сам.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

echo "[session-start] Готовлю окружение для тестов..."

APT_UPDATED=0
apt_refresh() {
    if [ "$APT_UPDATED" -eq 0 ]; then
        # Часть сторонних PPA в этом окружении закрыта прокси и сыпет warning
        # на каждый вызов — нужным репозиториям это не мешает, поэтому глушим
        # и не считаем за ошибку.
        apt-get update -qq 2>/dev/null || true
        APT_UPDATED=1
    fi
}

# ── 7-Zip: тесты собирают и распаковывают многотомный архив с паролем ──────
if command -v 7z >/dev/null 2>&1 || command -v 7zz >/dev/null 2>&1; then
    echo "[session-start] 7-Zip уже есть"
else
    echo "[session-start] Ставлю p7zip-full..."
    apt_refresh
    apt-get install -y -qq p7zip-full >/dev/null
fi

# unrar нужен блокноту, а не тестам, и лежит в multiverse — если нет, не беда.
if ! command -v unrar >/dev/null 2>&1; then
    apt_refresh
    apt-get install -y -qq unrar >/dev/null 2>&1 || \
        echo "[session-start] unrar недоступен, пропускаю (тестам он не нужен)"
fi

# ── PowerShell: тесты tools/mailru_cleanup.ps1 ────────────────────────────
# В apt по умолчанию его нет, репозиторий Microsoft надо подключить руками.
if command -v pwsh >/dev/null 2>&1; then
    echo "[session-start] PowerShell уже есть"
else
    echo "[session-start] Подключаю репозиторий Microsoft и ставлю PowerShell..."
    # shellcheck disable=SC1091
    . /etc/os-release
    DEB="/tmp/packages-microsoft-prod.deb"
    URL="https://packages.microsoft.com/config/${ID}/${VERSION_ID}/packages-microsoft-prod.deb"

    if curl -sSL --max-time 60 -o "$DEB" "$URL"; then
        dpkg -i "$DEB" >/dev/null 2>&1 || true
        rm -f "$DEB"
        APT_UPDATED=0  # появился новый репозиторий, нужен свежий индекс
        apt_refresh
        apt-get install -y -qq powershell >/dev/null 2>&1 || \
            echo "[session-start] PowerShell поставить не удалось — тесты очистителя пропустятся"
    else
        echo "[session-start] Не скачался $URL — тесты очистителя пропустятся"
    fi
fi

# ── Питон-зависимости ─────────────────────────────────────────────────────
echo "[session-start] Ставлю питон-зависимости..."
pip install -q --break-system-packages -r "${CLAUDE_PROJECT_DIR:-.}/requirements.txt" 2>/dev/null || \
    pip install -q -r "${CLAUDE_PROJECT_DIR:-.}/requirements.txt"

# ── Что получилось ────────────────────────────────────────────────────────
echo "[session-start] Итого:"
for tool in 7z unrar pwsh; do
    if command -v "$tool" >/dev/null 2>&1; then
        echo "  ✅ $tool"
    else
        echo "  ⏭  $tool отсутствует"
    fi
done
python3 -c "import requests, tqdm" 2>/dev/null \
    && echo "  ✅ requests, tqdm" \
    || echo "  ⏭  питон-зависимости не встали"

echo "[session-start] Готово. Тесты: python3 tools/selftest.py"
