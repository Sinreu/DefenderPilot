#requires -Version 5.1
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    python -m pip install -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости сборки.' }
    python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin --name DefenderPilot --add-data 'defenderpilot/defender.ps1;defenderpilot' app.py
    if ($LASTEXITCODE -ne 0) { throw 'Сборка EXE завершилась ошибкой.' }
    Write-Host 'Готово: dist\DefenderPilot.exe'
} finally { Pop-Location }
