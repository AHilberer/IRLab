cd C:\Users\HPS DYN\Documents\IRLab_control
.\venv\Scripts\activate

Write-Host "-----------------------------------------------------"
Write-Host "Starting spectro server ..."
Write-Host "-----------------------------------------------------"

uvicorn servers.spectro_server:app --host 192.168.1.2 --port 8002

