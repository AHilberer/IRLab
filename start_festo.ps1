.\.venv\Scripts\activate

Write-Host "-----------------------------------------------------"
Write-Host "Starting FESTO NI-DAQmx server ..."
Write-Host "-----------------------------------------------------"

uvicorn servers.festo_server:app --host 192.168.1.2 --port 8003
