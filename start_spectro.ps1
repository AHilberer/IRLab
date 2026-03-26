.\.venv\Scripts\activate

Write-Host "-----------------------------------------------------"
Write-Host "Starting spectro server ..."
Write-Host "-----------------------------------------------------"

uvicorn servers.spectro_server:app --host 192.168.1.3 --port 8002

