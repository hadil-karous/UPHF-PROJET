param([int]$Steps = 50)
$ErrorActionPreference = 'Stop'
if ($Steps -lt 1 -or $Steps -gt 50) { throw 'Use 1 to 50 steps: longer straight runs can leave the track.' }
$root = Split-Path $PSScriptRoot -Parent
$run = Join-Path $root ('results/scenario2-carla/' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force $run | Out-Null
docker cp "$PSScriptRoot/validate_gyrovia.py" exfmd-carla:/tmp/exfmd-validate.py
if ($LASTEXITCODE) { throw 'Copy failed' }
$remote = '/tmp/exfmd-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
docker exec exfmd-carla /opt/python310/bin/python3.10 /tmp/exfmd-validate.py --output $remote --steps $Steps
$code = $LASTEXITCODE
docker cp "exfmd-carla:${remote}/." $run
if ($LASTEXITCODE) { throw 'Results copy failed' }
Write-Output "Results: $run"
if ($code) { throw "Validation failed: $code" }
