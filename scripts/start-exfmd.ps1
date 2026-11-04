param([ValidateSet(1,3)][int]$Vehicles = 1,[switch]$OpenDashboard)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    docker compose -f docker/compose.runtime.yaml up -d
    if ($LASTEXITCODE) { throw 'Runtime containers could not start.' }
    $state = docker inspect exfmd-carla --format '{{.State.Running}}'
    if ($state -ne 'true') { docker start exfmd-carla; if ($LASTEXITCODE) { throw 'Existing CARLA failed to start.' } }
    $net = docker inspect exfmd-carla --format '{{json .NetworkSettings.Networks}}'
    if ($net -notmatch 'exfmd-runtime') { docker network connect exfmd-runtime exfmd-carla }
    docker exec exfmd-ros pgrep -f '^python3 /repo/scripts/run_integrated_demo.py$' | Out-Null
    if ($LASTEXITCODE -eq 0) { throw 'An integrated demo is already active.' }
    if (-not (Test-Path results/runtime-audit/deps/sumo/bin/sumo)) { throw 'Retained SUMO dependencies missing. See README_runtime.md.' }
    docker exec exfmd-ros bash /repo/scripts/prepare_ros.sh
    if ($LASTEXITCODE) { throw 'ROS/CARLA setup failed.' }
    $run = 'run-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    $dest = Join-Path $root "results/integrated/$run"
    New-Item -ItemType Directory -Force $dest | Out-Null
    $run | Set-Content results/current-run.txt
    & "$PSScriptRoot/start-dashboard.ps1" -Open:$OpenDashboard
    $artery = 'ulimit -c 0; python3 /repo/scripts/run_artery_diagnostic.py > /repo/results/integrated/' + $run + '/artery.log 2>&1'
    docker exec -d -e "EXFMD_RUN=$run" -e "EXFMD_VEHICLES=$Vehicles" exfmd-artery bash -lc $artery
    if ($LASTEXITCODE) { throw 'Artery launch failed.' }
    Start-Sleep -Seconds 3
    $ros = 'bash /repo/scripts/run_ros_demo.sh > /repo/results/integrated/' + $run + '/ros.log 2>&1'
    docker exec -e "EXFMD_RUN=$run" exfmd-ros bash -lc $ros
    $code = $LASTEXITCODE
    docker exec -e PYTHONPATH=/repo/results/runtime-audit/plot-deps exfmd-ros python3 /repo/scripts/export_plots.py
    if ($LASTEXITCODE) { Write-Warning 'Plot export unavailable; interactive dashboard remains available.' }
    Write-Output "Results: $dest"
    if ($code) { throw "Demo failed; inspect $dest/ros.log and artery.log." }
} finally { Pop-Location }
