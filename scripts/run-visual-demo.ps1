param([ValidateSet('Live','Replay')][string]$Mode='Live',[string]$Source='',
    [string]$Case=('a4-visual-'+(Get-Date -Format 'yyyyMMdd-HHmmss')),
    [ValidateRange(1,65535)][int]$Port=8767,[switch]$NoOpen)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python=(Get-Command python -ErrorAction Stop).Source
Push-Location $repo
try {
    if ($Mode -eq 'Live') {
        if ($Case -notmatch '^a4-visual-[a-zA-Z0-9_-]+$') { throw 'Invalid visual case name.' }
        if ((git branch --show-current) -ne 'a4-live-integration') { throw 'Switch to a4-live-integration.' }
        $Source=Join-Path $repo "results/phase4/$Case"
        if (Test-Path -LiteralPath $Source) { throw 'Evidence directory exists; choose a new case.' }
        docker info --format '{{.ServerVersion}}' | Out-Null
        if ($LASTEXITCODE) { throw 'Docker must be available for Live.' }
    } elseif (-not $Source) {
        foreach ($folder in (Get-ChildItem results/phase4 -Directory -Filter 'a4-visual-*' | Sort-Object Name -Descending)) {
            if (Test-Path (Join-Path $folder.FullName 'attempt-01/camera-frames.jsonl')) { $Source=$folder.FullName;break }
        }
    }
    if (-not $Source) { throw 'Provide -Source for a recorded visual run.' }
    if ([System.IO.Path]::IsPathRooted($Source)) { $Source=[System.IO.Path]::GetFullPath($Source) }
    else { $Source=[System.IO.Path]::GetFullPath((Join-Path $repo $Source)) }
    if ($Mode -eq 'Replay') {
        try {
            $existing=Invoke-RestMethod "http://127.0.0.1:$Port/api/data" -TimeoutSec 2
            $page=(Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/" -TimeoutSec 2).Content
            if ($existing.case -eq (Split-Path $Source -Leaf) -and $page.Contains('id="rgb"')) {
                if (-not $NoOpen) { Start-Process "http://127.0.0.1:$Port/" }
                Write-Output "Visual replay already open: http://127.0.0.1:$Port/";return
            }
        } catch {}
    }
    $listener=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,$Port)
    try { $listener.Start() } finally { $listener.Stop() }
    $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
    $logs=Join-Path $repo 'results/phase4';New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $viewerArgs=@('"'+(Join-Path $PSScriptRoot 'a4_dashboard.py')+'"','--source','"'+$Source+'"','--port',"$Port",'--visual')
    if ($Mode -eq 'Live') { $viewerArgs+='--live' }
    $viewer=Start-Process -FilePath $python -ArgumentList $viewerArgs -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logs/visual-web-$stamp.log" -RedirectStandardError "$logs/visual-web-$stamp-error.log"
    $engine=$null
    $control=[ordered]@{source=$Source;url="http://127.0.0.1:$Port/";viewer_pid=$viewer.Id;engine_pid=$null;mode=$Mode}
    $ready=$false
    for ($i=0;$i -lt 30;$i++) {
        try { $ready=(Invoke-WebRequest -UseBasicParsing $control.url -TimeoutSec 2).StatusCode -eq 200 } catch {}
        if ($ready) { break };Start-Sleep -Milliseconds 200
    }
    if (-not $ready) { Stop-Process -Id $viewer.Id;throw 'Visual server did not start.' }
    if ($Mode -eq 'Live') {
        $engineArgs=@('"'+(Join-Path $PSScriptRoot 'a4_demo.py')+'"','--case',$Case,'--visual')
        $engine=Start-Process -FilePath $python -ArgumentList $engineArgs -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logs/visual-engine-$stamp.log" -RedirectStandardError "$logs/visual-engine-$stamp-error.log"
        $control.engine_pid=$engine.Id
    }
    $control | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $logs 'visual-control-current.json')
    $control | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $logs "visual-control-$stamp.json")
    if (-not $NoOpen) { Start-Process $control.url }
    Write-Output "Visible demo: $($control.url)"
    Write-Output "Mode: $Mode. CARLA startup may take several minutes. The replay loops automatically after acquisition."
    Write-Output 'Stop: .\scripts\stop-visual-demo.ps1'
} finally { Pop-Location }
