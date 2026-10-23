# Create the Python virtual environment (.venv) of IRLab without Internet access, from the
# packages downloaded by tools\download_wheels.ps1. Run on each bench PC, with Python 3.13
# installed (py launcher):
#   .\tools\install_offline.ps1                   # packages in wheels\ in the repository
#   .\tools\install_offline.ps1 -Wheels E:\wheels # or in any other folder (USB key...)
# An existing .venv is never overwritten: rename it first (Rename-Item .venv .venv_old).
param([string]$Wheels = 'wheels')

$PythonVersion = '3.13'
# modules imported to check the installation
$Modules = 'fastapi, uvicorn, serial, yaml, numpy, h5py, requests, IPython, nidaqmx'

Set-Location (Split-Path $PSScriptRoot -Parent)
$Python = '.venv\Scripts\python.exe'

function Fail($Message) {
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

# Checks first: nothing is changed if one of them fails
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Fail "the py launcher was not found: install Python $PythonVersion (see README.md, section Installation)."
}
$Version = & py -$PythonVersion -c "import sys; print(sys.version.split()[0])" 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail "Python $PythonVersion was not found (py -$PythonVersion): install it (see README.md, section Installation)."
}
if (-not (Test-Path $Wheels -PathType Container)) {
    Fail "package folder not found: $Wheels (give it with -Wheels <folder>)."
}
if (Test-Path .venv) {
    Fail ".venv already exists: rename it first (Rename-Item .venv .venv_old), then run this script again."
}

function Fail-And-Clean($Message) {
    # remove the incomplete .venv, so the script can be run again
    Remove-Item .venv -Recurse -Force -ErrorAction SilentlyContinue
    Fail "$Message The incomplete .venv was removed (restore .venv_old if needed)."
}

Write-Host "-----------------------------------------------------"
Write-Host "Creating .venv with Python $Version ..."
Write-Host "-----------------------------------------------------"
& py -$PythonVersion -m venv .venv
if ($LASTEXITCODE -ne 0) {
    Fail-And-Clean "creation of .venv failed."
}

Write-Host "Installing the packages of requirements.txt from $Wheels ..."
# --no-index: never look for packages on the Internet
& $Python -m pip install --no-index --find-links $Wheels -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Fail-And-Clean "installation failed (see the pip message above)."
}

Write-Host "Checking the installation..."
& $Python -m pip check
if ($LASTEXITCODE -ne 0) {
    Fail-And-Clean "inconsistent dependencies (see the pip message above)."
}
& $Python -c "import $Modules"
if ($LASTEXITCODE -ne 0) {
    Fail-And-Clean "a module cannot be imported (see the message above)."
}

$Count = (& $Python -m pip list --format=freeze | Measure-Object -Line).Lines
Write-Host "-----------------------------------------------------"
Write-Host "OK: .venv created with Python $Version, $Count packages installed." -ForegroundColor Green
Write-Host "Next: start the servers of this PC (.\start_motion.ps1...) or the shell."
Write-Host "FESTO PC: the NI-DAQmx driver must also be installed (the nidaqmx package alone is not enough)."
Write-Host "-----------------------------------------------------"
