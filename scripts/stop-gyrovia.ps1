$ErrorActionPreference = 'Stop'
docker cp "$PSScriptRoot/stop_validation.py" exfmd-carla:/tmp/exfmd-stop.py
docker exec exfmd-carla /opt/python310/bin/python3.10 /tmp/exfmd-stop.py
