param([switch]$StopDashboard)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
docker exec exfmd-ros python3 /repo/scripts/stop_integrated.py
docker exec exfmd-artery python3 /repo/scripts/stop_integrated.py
# Give bounded Python cleanup time before stopping these two project containers.
Start-Sleep -Seconds 5
docker stop --timeout 10 exfmd-ros exfmd-artery
if ($StopDashboard) {
    $servers = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match 'ExFMD-CP[\\/]scripts[\\/]results_server\.py' }
    foreach ($server in $servers) { Stop-Process -Id $server.ProcessId }
}
Write-Output 'ROS/Artery stopped. CARLA and unrelated containers preserved.'
