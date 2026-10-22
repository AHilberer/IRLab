# Start the FESTO NI-DAQmx server on this PC.
# Listens on all network interfaces; the port comes from config/servers.yaml
# (festo_server), unless given explicitly: .\start_festo.ps1 -Port 8003
# Can be launched from any directory (also from a scheduled task, see docs/TECHNICAL.md).
param([int]$Port = 0)

Set-Location $PSScriptRoot
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    Write-Host "ERROR: Python virtual environment not found: $Python" -ForegroundColor Red
    Write-Host "Create it first (see README.md, section Installation)." -ForegroundColor Red
    exit 1
}

if (-not $Port) {
    $Port = & $Python -c "from common.servers import get_server_port; print(get_server_port('festo_server', env_var='FESTO_SERVER', default=8003))"
    if ($LASTEXITCODE -ne 0 -or -not $Port) {
        Write-Host "ERROR: cannot read the port of festo_server from config/servers.yaml" -ForegroundColor Red
        exit 1
    }
}

Write-Host "-----------------------------------------------------"
Write-Host "Starting FESTO NI-DAQmx server on port $Port ..."
Write-Host "-----------------------------------------------------"

& $Python -m uvicorn servers.festo_server:app --host 0.0.0.0 --port $Port
exit $LASTEXITCODE
