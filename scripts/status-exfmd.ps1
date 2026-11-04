$ErrorActionPreference = 'Stop'
docker ps -a --filter name=exfmd- --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
try { $s=Invoke-RestMethod http://127.0.0.1:8765/api/status -TimeoutSec 3; Write-Output $s.note } catch { Write-Output 'Dashboard not responding.' }
docker exec exfmd-ros pgrep -af '^python3 /repo/scripts/run_integrated_demo.py$'
if ($LASTEXITCODE -ne 0) { Write-Output 'No integrated demo active; displayed results are recorded.' }
