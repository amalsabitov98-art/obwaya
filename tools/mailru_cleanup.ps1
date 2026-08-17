<#
Очистка облака Mail.ru после переноса в Google Drive.

Удаляет из Mail.ru то, что уже скопировано — но только если сверка показала
полное совпадение. Если хоть один файл не доехал, скрипт откажется удалять.

    .\mailru_cleanup.ps1                  # сверить и спросить подтверждение
    .\mailru_cleanup.ps1 -DryRun          # только показать, что удалилось бы
    .\mailru_cleanup.ps1 -Source mailru:Фото -Dest "gdrive:Из Mail.ru Облака/Фото"

Запускать из папки с rclone.exe.
#>

param(
    [string]$Source = "mailru:",
    [string]$Dest = "gdrive:Из Mail.ru Облака",
    [string]$Rclone = ".\rclone.exe",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Rclone)) {
    Write-Host "Не нашёл $Rclone. Запусти скрипт из папки, где лежит rclone.exe," -ForegroundColor Red
    Write-Host "либо укажи путь: -Rclone C:\rclone\rclone.exe" -ForegroundColor Red
    exit 1
}

# ── Шаг 1: сверка ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Сверяю $Source с $Dest ..." -ForegroundColor Cyan
Write-Host "Сравнение по размерам: Mail.ru и Google считают контрольные суммы"
Write-Host "по-разному, побайтово сверить не получится."
Write-Host ""

& $Rclone check $Source $Dest --one-way --size-only
$checkCode = $LASTEXITCODE

if ($checkCode -ne 0) {
    Write-Host ""
    Write-Host "СТОП. Сверка не прошла (код $checkCode)." -ForegroundColor Red
    Write-Host "Значит, что-то не доехало в Drive. Ничего не удаляю." -ForegroundColor Red
    Write-Host ""
    Write-Host "Докопируй остаток и запусти скрипт снова:"
    Write-Host "  $Rclone copy $Source `"$Dest`" --progress --transfers 4 --retries 5"
    exit 1
}

Write-Host ""
Write-Host "Сверка чистая: всё из Mail.ru лежит в Drive." -ForegroundColor Green

# ── Шаг 2: что будет удалено ────────────────────────────────────────────────
Write-Host ""
Write-Host "Объём, который освободится в Mail.ru:" -ForegroundColor Cyan
& $Rclone size $Source

if ($DryRun) {
    Write-Host ""
    Write-Host "Пробный режим: показываю, что удалилось бы." -ForegroundColor Yellow
    & $Rclone delete $Source --dry-run
    Write-Host ""
    Write-Host "Ничего не удалено. Убери -DryRun, чтобы удалить по-настоящему." -ForegroundColor Yellow
    exit 0
}

# ── Шаг 3: подтверждение ────────────────────────────────────────────────────
Write-Host ""
Write-Host "Сейчас файлы будут удалены из $Source. Отменить это будет нельзя." -ForegroundColor Yellow
Write-Host "Копия в Drive остаётся — её скрипт не трогает." -ForegroundColor Yellow
Write-Host ""
$answer = Read-Host "Напиши УДАЛИТЬ, чтобы продолжить"

if ($answer -ne "УДАЛИТЬ") {
    Write-Host "Отменено, ничего не удалено." -ForegroundColor Green
    exit 0
}

# ── Шаг 4: удаление ─────────────────────────────────────────────────────────
Write-Host ""
& $Rclone delete $Source --progress
$deleteCode = $LASTEXITCODE

Write-Host ""
& $Rclone rmdirs $Source --leave-root

if ($deleteCode -ne 0) {
    Write-Host ""
    Write-Host "Удаление вернуло код $deleteCode — что-то удалилось не всё." -ForegroundColor Yellow
    Write-Host "Запусти скрипт снова, он добьёт остаток." -ForegroundColor Yellow
    exit $deleteCode
}

Write-Host ""
Write-Host "Готово. Файлы удалены из Mail.ru." -ForegroundColor Green
Write-Host ""
Write-Host "ВАЖНО: место освободится не сразу." -ForegroundColor Yellow
Write-Host "Mail.ru складывает удалённое в Корзину, и оно продолжает занимать"
Write-Host "квоту. Зайди на cloud.mail.ru, открой Корзину и очисти её — только"
Write-Host "после этого переполнение снимется."
