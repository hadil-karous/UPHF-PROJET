param([string]$Case = ('a1-e2e-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if ($Case -notmatch '^a1-e2e-[a-zA-Z0-9_-]+$') { throw 'Invalid case name.' }
Push-Location $repo
$started = @()
$priorTestDir = $env:EXFMD_CPM_TEST_DIR
try {
    if ((git branch --show-current) -ne 'fix/cpm-f2md-integration') { throw 'Switch to fix/cpm-f2md-integration first.' }
    $destination = Join-Path $repo "results/phase1/$Case"
    if (Test-Path -LiteralPath $destination) { throw 'Evidence directory already exists; use a new case name.' }
    New-Item -ItemType Directory -Path $destination | Out-Null
    foreach ($name in @('exfmd-cpm-a1','exfmd-carla','exfmd-artery','exfmd-ros')) {
        $state = docker inspect $name --format '{{.State.Running}}'
        if ($LASTEXITCODE) { throw "Missing $name; prepare the project runtime and the isolated build container first." }
        if ($state -ne 'true') { $started += $name }
    }
    $builderImage = docker inspect exfmd-cpm-a1 --format '{{.Image}}'
    $runtimeImage = docker inspect exfmd-artery --format '{{.Image}}'
    if ($builderImage -ne $runtimeImage) { throw 'Builder/runtime Artery images differ; review ABI first.' }
    if ($started -contains 'exfmd-cpm-a1') {
        docker start exfmd-cpm-a1 | Out-Null
        if ($LASTEXITCODE) { throw 'Cannot start isolated builder.' }
    }
    docker exec exfmd-cpm-a1 test -x /evidence/decode_cpm
    if ($LASTEXITCODE) { throw 'The Vanetza decoder from the previous A1 step is required.' }
    $env:EXFMD_CPM_TEST_DIR = Join-Path $destination 'unit-tests'
    & C:\Python38\python.exe scripts/cpm/run_python_tests.py
    if ($LASTEXITCODE) { throw 'Python tests failed; no live scenario.' }
    docker exec -e "EXFMD_CPM_BUILD_DIR=/evidence/$Case/build" exfmd-cpm-a1 python3 /repo/scripts/cpm/build_component.py
    if ($LASTEXITCODE) { throw 'Component build failed; no live scenario.' }
    & C:\Python38\python.exe scripts/cpm/live_run.py --case $Case
    if ($LASTEXITCODE) { throw 'Live scenario failed; evidence retained.' }
    & C:\Python38\python.exe scripts/cpm/validate_live.py --attempt "results/phase1/$Case/attempt-01"
    if ($LASTEXITCODE) { throw 'Live data comparisons failed; evidence retained.' }
    Write-Output "Evidence: $destination"
} finally {
    $env:EXFMD_CPM_TEST_DIR = $priorTestDir
    if ($started.Count) { docker stop $started | Out-Null }
    Pop-Location
}
