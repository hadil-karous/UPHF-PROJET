$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
docker cp "$root/cosimulation/sumo-integration/carla/Co-Simulation/Sumo/." exfmd-carla:/tmp/exfmd-sumo
docker cp "$PSScriptRoot/validate_cosimulation.py" exfmd-carla:/tmp/exfmd-cosim.py
docker exec -e PYTHONPATH=/tmp/exfmd-deps:/tmp/exfmd-deps/sumo/tools -e SUMO_HOME=/tmp/exfmd-deps/sumo -e PATH=/tmp/exfmd-deps/sumo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin exfmd-carla /opt/python310/bin/python3.10 /tmp/exfmd-cosim.py
$code = $LASTEXITCODE
$dest = Join-Path $root ('results/cosimulation/' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force $dest | Out-Null
docker cp exfmd-carla:/tmp/exfmd-cosim-results/. $dest
Write-Output "Results: $dest"
if ($code) { throw 'Co-simulation failed' }
