# Start the IRLab shell on this PC (any PC of the bench).
# Can be launched from any directory: .\start_shell.ps1 or & "C:\<path>\IRLab\start_shell.ps1"
Set-Location $PSScriptRoot
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    Write-Host "ERROR: Python virtual environment not found: $Python" -ForegroundColor Red
    Write-Host "Create it first (see README.md, section Installation)." -ForegroundColor Red
    exit 1
}

& $Python IRLab_shell.py
exit $LASTEXITCODE
