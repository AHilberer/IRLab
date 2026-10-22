# Start the motion server on this PC.
# Listens on all network interfaces; the port comes from config/servers.yaml
# (motion_server), unless given explicitly: .\start_motion.ps1 -Port 8001
param([int]$Port = 0)

Set-Location $PSScriptRoot
.\.venv\Scripts\activate

if (-not $Port) {
    $Port = python -c "from common.servers import get_server_port; print(get_server_port('motion_server', env_var='MOTION_SERVER', default=8001))"
}

Write-Host "-----------------------------------------------------"
Write-Host "Starting motion server on port $Port ..."
Write-Host "-----------------------------------------------------"

uvicorn servers.motion_server:app --host 0.0.0.0 --port $Port
