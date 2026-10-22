# Start the FESTO NI-DAQmx server on this PC.
# Listens on all network interfaces; the port comes from config/servers.yaml
# (festo_server), unless given explicitly: .\start_festo.ps1 -Port 8003
param([int]$Port = 0)

Set-Location $PSScriptRoot
.\.venv\Scripts\activate

if (-not $Port) {
    $Port = python -c "from common.servers import get_server_port; print(get_server_port('festo_server', env_var='FESTO_SERVER', default=8003))"
}

Write-Host "-----------------------------------------------------"
Write-Host "Starting FESTO NI-DAQmx server on port $Port ..."
Write-Host "-----------------------------------------------------"

uvicorn servers.festo_server:app --host 0.0.0.0 --port $Port
