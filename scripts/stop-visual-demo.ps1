$ErrorActionPreference='Stop'
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$control=Get-Content -LiteralPath (Join-Path $repo 'results/phase4/visual-control-current.json') -Raw | ConvertFrom-Json
& (Get-Command python).Source (Join-Path $PSScriptRoot 'stop_visual.py')
if ($control.engine_pid -and (Get-CimInstance Win32_Process -Filter "ProcessId=$($control.engine_pid)" -ErrorAction SilentlyContinue).CommandLine -like '*a4_demo.py*') {
    Wait-Process -Id $control.engine_pid -Timeout 45 -ErrorAction SilentlyContinue
}
$viewer=Get-CimInstance Win32_Process -Filter "ProcessId=$($control.viewer_pid)" -ErrorAction SilentlyContinue
if ($viewer -and $viewer.CommandLine -like '*a4_dashboard.py*' -and $viewer.CommandLine.Replace('/','\').Contains($control.source.Replace('/','\'))) { Stop-Process -Id $control.viewer_pid }
Write-Output 'Viewer stopped; saved RGB sequences remain available in Replay.'
