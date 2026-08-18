<#
Clean up Mail.ru cloud after it has been mirrored to Google Drive.

Deletes files from Mail.ru, but ONLY if a fresh check shows the Drive copy
matches completely. If even one file is missing on the Drive side, the
script refuses to delete anything.

All output is in English on purpose: this file is downloaded and re-saved
across systems, and non-ASCII text has broken before due to encoding
mismatches between how it was written and how Windows PowerShell reads it.
Plain ASCII can't suffer that problem.

    .\mailru_cleanup.ps1 -Dest "gdrive:Your Drive Folder"              # check, then ask before deleting
    .\mailru_cleanup.ps1 -Dest "gdrive:Your Drive Folder" -DryRun      # only show what would be deleted
    .\mailru_cleanup.ps1 -Source mailru:Photos -Dest "gdrive:Backup/Photos"

Run this from the folder that contains rclone.exe.

-Dest has no default on purpose, even though it's easy to hardcode the
folder name most people using this script will actually have (something
with non-ASCII characters in it, like a Cyrillic folder name). This file
gets downloaded and re-saved across systems, and any non-ASCII text
embedded in it is at risk of encoding corruption turning into a syntax
error or, worse, a silently wrong path. Typing -Dest yourself at your own
PowerShell prompt uses your console's own encoding and can't be corrupted
that way. This entire file is kept pure ASCII for the same reason.
#>

param(
    [string]$Source = "mailru:",
    [string]$Dest = "",
    [string]$Rclone = ".\rclone.exe",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Dest)) {
    Write-Host "Missing -Dest. Pass the exact Google Drive folder you copied into, for example:" -ForegroundColor Red
    Write-Host "  .\mailru_cleanup.ps1 -Dest `"gdrive:Your Drive Folder`"" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Rclone)) {
    Write-Host "Can't find $Rclone. Run this script from the folder that has rclone.exe," -ForegroundColor Red
    Write-Host "or pass the path explicitly: -Rclone C:\rclone\rclone.exe" -ForegroundColor Red
    exit 1
}

# -- Step 1: verify -----------------------------------------------------------
Write-Host ""
Write-Host "Checking $Source against $Dest ..." -ForegroundColor Cyan
Write-Host "Comparing by size only: Mail.ru and Google compute checksums"
Write-Host "differently, so a byte-for-byte hash check isn't possible."
Write-Host ""

& $Rclone check $Source $Dest --one-way --size-only
$checkCode = $LASTEXITCODE

if ($checkCode -ne 0) {
    Write-Host ""
    Write-Host "STOP. The check failed (exit code $checkCode)." -ForegroundColor Red
    Write-Host "That means something hasn't made it to Drive yet. Deleting nothing." -ForegroundColor Red
    Write-Host ""
    Write-Host "Copy the rest and run this script again:"
    Write-Host "  $Rclone copy $Source `"$Dest`" --progress --transfers 4 --retries 5"
    exit 1
}

Write-Host ""
Write-Host "Check passed: everything from Mail.ru is already in Drive." -ForegroundColor Green

# -- Step 2: preview what will be freed ---------------------------------------
Write-Host ""
Write-Host "Space that will be freed on Mail.ru:" -ForegroundColor Cyan
& $Rclone size $Source

if ($DryRun) {
    Write-Host ""
    Write-Host "Dry run: showing what would be deleted, nothing is touched." -ForegroundColor Yellow
    & $Rclone delete $Source --dry-run
    Write-Host ""
    Write-Host "Nothing was deleted. Drop -DryRun to actually delete." -ForegroundColor Yellow
    exit 0
}

# -- Step 3: confirm ------------------------------------------------------------
Write-Host ""
Write-Host "Files are about to be permanently deleted from $Source." -ForegroundColor Yellow
Write-Host "This cannot be undone. The copy in Drive is not touched." -ForegroundColor Yellow
Write-Host ""
$answer = Read-Host "Type DELETE (in capitals) to continue"

if ($answer -ne "DELETE") {
    Write-Host "Cancelled, nothing was deleted." -ForegroundColor Green
    exit 0
}

# -- Step 4: delete ---------------------------------------------------------
Write-Host ""
& $Rclone delete $Source --progress
$deleteCode = $LASTEXITCODE

Write-Host ""
& $Rclone rmdirs $Source --leave-root

if ($deleteCode -ne 0) {
    Write-Host ""
    Write-Host "Delete returned exit code $deleteCode - something may not have been removed." -ForegroundColor Yellow
    Write-Host "Run this script again, it will finish the rest." -ForegroundColor Yellow
    exit $deleteCode
}

Write-Host ""
Write-Host "Done. Files deleted from Mail.ru." -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: your quota will not free up right away." -ForegroundColor Yellow
Write-Host "Mail.ru moves deleted files to Trash, and Trash still counts against"
Write-Host "your quota. Go to cloud.mail.ru, open Trash, and empty it - only"
Write-Host "then will the over-quota warning actually clear."
