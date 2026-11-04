param([switch]$Open)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$url = 'http://127.0.0.1:8765/dashboard/'
$ready = $false
try { $ready = (Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 2).StatusCode -eq 200 } catch {}
if (-not $ready) {
    $python = (Get-Command python -ErrorAction Stop).Source
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $proc = Start-Process -FilePath $python -ArgumentList "$PSScriptRoot/results_server.py" -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput "$root/results/dashboard/server-$stamp.log" -RedirectStandardError "$root/results/dashboard/server-$stamp-error.log" -PassThru
    $proc.Id | Set-Content "$root/results/dashboard/server.pid"
    for ($i=0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 500
        try { if ((Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 2).StatusCode -eq 200) { $ready=$true; break } } catch {}
    }
}
if (-not $ready) { throw 'Dashboard did not start. Check results/dashboard/server-*-error.log.' }
Write-Output $url
if ($Open) { Start-Process $url }
