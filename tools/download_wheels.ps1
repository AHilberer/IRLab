# Download the Python packages of requirements.txt for an offline installation.
# Run on a Windows PC connected to the Internet, with Python 3.13 installed (py launcher):
#   .\tools\download_wheels.ps1                  # into wheels\ in the repository
#   .\tools\download_wheels.ps1 -Dest E:\wheels  # or any other folder (USB key...)
# Then copy the folder to the bench PCs and run tools\install_offline.ps1 there.
# Existing files of the folder are kept: only the missing packages are downloaded.
param([string]$Dest = 'wheels')

$PythonVersion = '3.13'

Set-Location (Split-Path $PSScriptRoot -Parent)

function Fail($Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Fail "the py launcher was not found: install Python $PythonVersion (see README.md, section Installation)."
}
& py -$PythonVersion -c "import sys" 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail "Python $PythonVersion was not found (py -$PythonVersion): install it (see README.md, section Installation)."
}

Write-Host "-----------------------------------------------------"
Write-Host "Downloading the packages of requirements.txt into $Dest ..."
Write-Host "-----------------------------------------------------"
# --no-deps: exactly the fixed list, nothing else; --only-binary: nothing to compile on the bench
& py -$PythonVersion -m pip download -r requirements.txt -d $Dest --no-deps --only-binary=:all: `
    --platform win_amd64 --python-version $PythonVersion --implementation cp
if ($LASTEXITCODE -ne 0) {
    Fail "download failed (see the pip message above)."
}

Write-Host "-----------------------------------------------------"
Write-Host "Checking that the folder is enough for an offline installation..."
Write-Host "-----------------------------------------------------"
# simulated offline installation: fails if a dependency is missing from requirements.txt
& py -$PythonVersion -m pip install --dry-run --ignore-installed --no-index --find-links $Dest -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Fail "the folder is not enough for an offline installation: a dependency is probably missing from requirements.txt (see the pip message above)."
}

$Files = Get-ChildItem $Dest -File
$SizeMB = [math]::Round(($Files | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Host "-----------------------------------------------------"
Write-Host "OK: $($Files.Count) files, $SizeMB MB in $Dest" -ForegroundColor Green
Write-Host "Next: copy this folder to the bench PCs, then run tools\install_offline.ps1 on each."
Write-Host "-----------------------------------------------------"
