param(
    [ValidateSet('Live','Replay')][string]$Mode='Live',
    [string]$Case=('a4-live-'+(Get-Date -Format 'yyyyMMdd-HHmmss')),
    [string]$Source='',
    [ValidateRange(1,65535)][int]$Port=8766,
    [switch]$NoDashboard,
    [switch]$Open
)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python=(Get-Command python -ErrorAction Stop).Source
$watch=$null
Push-Location $repo
try {
    if ($Mode -eq 'Live' -and -not $NoDashboard) {
        # The viewer can watch an evidence directory before it is created.
        # It changes from LIVE to REPLAY as soon as the recorded session ends.
        $Source=Join-Path $repo "results/phase4/$Case"
        $watchArgs=@('"'+(Join-Path $PSScriptRoot 'a4_dashboard.py')+'"','--source','"'+$Source+'"','--port',"$Port",'--live')
        $listener=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,$Port)
        try { $listener.Start() } finally { $listener.Stop() }
        $logs=Join-Path $repo 'results/phase4';New-Item -ItemType Directory -Path $logs -Force | Out-Null
        $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
        $watch=Start-Process -FilePath $python -ArgumentList $watchArgs -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logs/dashboard-$stamp.log" -RedirectStandardError "$logs/dashboard-$stamp-error.log"
        [pscustomobject]@{pid=$watch.Id;url="http://127.0.0.1:$Port/";source=$Source;mode='Live then Replay'} | ConvertTo-Json | Set-Content -Encoding UTF8 "$logs/dashboard-$stamp.json"
        Write-Output "LIVE dashboard: http://127.0.0.1:$Port/ (PID $($watch.Id))"
        if ($Open) { Start-Process "http://127.0.0.1:$Port/" }
    }
    if ($Mode -eq 'Live') {
        & $python scripts/a4_demo.py --case $Case
        if ($LASTEXITCODE) { throw "A4 live failed; see results/phase4/$Case. No success claimed." }
        $Source=Join-Path $repo "results/phase4/$Case"
        if ($watch) { Write-Output "Replay ready: http://127.0.0.1:$Port/; stop viewer: Stop-Process -Id $($watch.Id)"; return }
    } elseif (-not $Source) {
        $candidates=Get-ChildItem -LiteralPath (Join-Path $repo 'results/phase4') -Directory | Sort-Object Name -Descending
        foreach ($item in $candidates) {
            $validation=Join-Path $item.FullName 'attempt-01/validation-a4.json'
            if ((Test-Path -LiteralPath $validation) -and (Get-Content -LiteralPath $validation -Raw | ConvertFrom-Json).passed) { $Source=$item.FullName; break }
        }
    }
    if (-not $Source) { throw 'Provide -Source pointing to a validated A4 evidence directory.' }
    $Source=(Resolve-Path -LiteralPath $Source).Path
    if ($NoDashboard) { Write-Output $Source; return }
    try {
        $existing=Invoke-RestMethod "http://127.0.0.1:$Port/api/data" -TimeoutSec 2
        if ($existing.case -eq (Split-Path $Source -Leaf)) {
            Write-Output "Dashboard already available: http://127.0.0.1:$Port/"
            if ($Open) { Start-Process "http://127.0.0.1:$Port/" }
            return
        }
    } catch {}
    $listener=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,$Port)
    try { $listener.Start() } finally { $listener.Stop() }
    $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
    $logs=Join-Path $repo 'results/phase4';New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $argsList=@('"'+(Join-Path $PSScriptRoot 'a4_dashboard.py')+'"','--source','"'+$Source+'"','--port',"$Port")
    $server=Start-Process -FilePath $python -ArgumentList $argsList -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logs/dashboard-$stamp.log" -RedirectStandardError "$logs/dashboard-$stamp-error.log"
    $url="http://127.0.0.1:$Port/"
    $ready=$false
    for ($i=0;$i -lt 20;$i++) {
        try { $ready=(Invoke-WebRequest -UseBasicParsing ($url+'api/data') -TimeoutSec 2).StatusCode -eq 200 } catch {}
        if ($ready) { break }; Start-Sleep -Milliseconds 250
    }
    if (-not $ready) { Stop-Process -Id $server.Id -ErrorAction SilentlyContinue; throw 'Dashboard failed to start.' }
    [pscustomobject]@{pid=$server.Id;url=$url;source=$Source;mode='Replay'} | ConvertTo-Json | Set-Content -Encoding UTF8 "$logs/dashboard-$stamp.json"
    Write-Output "Dashboard: $url (PID $($server.Id); stop: Stop-Process -Id $($server.Id))"
    if ($Open) { Start-Process $url }
} finally { Pop-Location }
