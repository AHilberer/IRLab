cd C:\Users\HPS DYN\Documents\IRLab_control
.\venv\Scripts\activate

Write-Host "-----------------------------------------------------"
Write-Host "Starting motion server ..."
Write-Host "-----------------------------------------------------"

uvicorn servers.motion_server:app --host 192.168.1.2 --port 8001

