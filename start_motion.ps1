.\.venv\Scripts\activate

Write-Host "-----------------------------------------------------"
Write-Host "Starting motion server ..."
Write-Host "-----------------------------------------------------"

uvicorn servers.motion_server:app --host 192.168.1.3 --port 8001

