param([string]$Case = ('a2-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if ($Case -notmatch '^a2-[a-zA-Z0-9_-]+$') { throw 'Invalid case name.' }
Push-Location $root
$wasRunning = $true
try {
    if ((git branch --show-current) -ne 'fix/cpm-f2md-integration') { throw 'Expected fix/cpm-f2md-integration branch.' }
    $path = Join-Path $root "results/phase1/$Case"
    if (Test-Path -LiteralPath $path) { throw 'Case already exists; choose a new case name.' }
    New-Item -ItemType Directory -Path $path | Out-Null
    $image = docker inspect exfmd-cpm-a1 --format '{{.Image}}'
    if ($LASTEXITCODE -or $image -ne 'sha256:333eddecf31deda29368a7512074dc959ece026155ced270ebb763c1278fb511') { throw 'Prepared isolated Artery container/image required.' }
    $wasRunning = (docker inspect exfmd-cpm-a1 --format '{{.State.Running}}') -eq 'true'
    if (-not $wasRunning) { docker start exfmd-cpm-a1 | Out-Null; if ($LASTEXITCODE) { throw 'Builder did not start.' } }
    docker exec -e "EXFMD_A2_BUILD=/evidence/$Case/build" -e EXFMD_A1_CORE=/repo/results/phase1/a1-e2e-20261106-161848/build/libartery_core.so exfmd-cpm-a1 python3 /repo/scripts/cpm/a2_build.py
    if ($LASTEXITCODE) { throw 'A2 build/unit tests failed; no replay.' }
    docker exec -e "EXFMD_A2_CASE=/evidence/$Case" exfmd-cpm-a1 python3 /repo/scripts/cpm/a2_recorded.py
    if ($LASTEXITCODE) { throw 'Recorded corpus failed; no native scenario.' }
    docker exec -e "EXFMD_A2_CASE=/evidence/$Case" exfmd-cpm-a1 python3 /repo/scripts/cpm/a2_native.py
    if ($LASTEXITCODE) { throw 'Native A2 integration failed; evidence retained.' }
    docker exec -e "EXFMD_A2_CASE=/evidence/$Case" exfmd-cpm-a1 python3 /repo/scripts/cpm/a2_verify_native.py
    if ($LASTEXITCODE) { throw 'Native field/control comparisons failed.' }
    Write-Output "A2 evidence: $path"
} finally {
    if (-not $wasRunning) { docker stop exfmd-cpm-a1 | Out-Null }
    Pop-Location
}
