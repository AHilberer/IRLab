# Start the spectro server on this PC.
# Listens on all network interfaces; the port comes from config/servers.yaml
# (spectro_server), unless given explicitly: .\start_spectro.ps1 -Port 8002
param([int]$Port = 0)

Set-Location $PSScriptRoot
.\.venv\Scripts\activate

if (-not $Port) {
    $Port = python -c "from common.servers import get_server_port; print(get_server_port('spectro_server', env_var='SPECTRO_SERVER', default=8002))"
}

Write-Host "-----------------------------------------------------"
Write-Host "Starting spectro server on port $Port ..."
Write-Host "-----------------------------------------------------"

uvicorn servers.spectro_server:app --host 0.0.0.0 --port $Port
