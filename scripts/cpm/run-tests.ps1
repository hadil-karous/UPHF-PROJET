param([switch]$Integration)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$dest = Join-Path $repo 'results/phase1'
$container = 'exfmd-cpm-a1'
Push-Location $repo
try {
    $image = docker image inspect sarra13ba/exfmd-artery:1.0 --format '{{.Id}}'
    if ($LASTEXITCODE) { throw 'Artery image or Docker engine unavailable.' }
    if ($image -ne 'sha256:333eddecf31deda29368a7512074dc959ece026155ced270ebb763c1278fb511') { throw 'Unexpected image version; review ABI before building.' }
    $exists = docker ps -a --filter "name=^/$container$" --format '{{.Names}}'
    if (-not $exists) {
        docker run -d --name $container --network none --mount "type=bind,source=$repo,target=/repo,readonly" --mount "type=bind,source=$dest,target=/evidence" sarra13ba/exfmd-artery:1.0 sleep infinity
        if ($LASTEXITCODE) { throw 'Isolated container creation failed.' }
    } else {
        $state = (docker inspect $container | ConvertFrom-Json)[0]
        $repoMount = @($state.Mounts | Where-Object { $_.Destination -eq '/repo' })
        $evidenceMount = @($state.Mounts | Where-Object { $_.Destination -eq '/evidence' })
        if ($state.Image -ne $image -or $state.HostConfig.NetworkMode -ne 'none' -or $repoMount.Count -ne 1 -or $repoMount[0].RW -or $evidenceMount.Count -ne 1) { throw 'Existing container does not match isolated test configuration.' }
        if (-not $state.State.Running) { docker start $container | Out-Null; if ($LASTEXITCODE) { throw 'Container start failed.' } }
    }
    New-Item -ItemType Directory -Force (Join-Path $dest 'corrections') | Out-Null
    & C:\Python38\python.exe scripts/cpm/run_python_tests.py | Tee-Object (Join-Path $dest 'corrections/python-tests.log')
    if ($LASTEXITCODE) { throw 'Python tests failed; no integration run.' }
    docker exec $container bash /repo/scripts/cpm/inspect_image.sh
    if ($LASTEXITCODE) { throw 'Saved packet decode failed.' }
    docker exec $container bash /repo/scripts/cpm/build_and_test.sh
    if ($LASTEXITCODE) { throw 'ASN.1 unit tests failed; no integration run.' }
    docker exec $container python3 /repo/scripts/cpm/compare_recorded.py
    if ($LASTEXITCODE) { throw 'Recorded corpus decode failed.' }
    docker exec $container python3 /repo/scripts/cpm/build_component.py
    if ($LASTEXITCODE) { throw 'Component build failed; no integration run.' }
    docker exec $container python3 /repo/scripts/cpm/runtime.py
    if ($LASTEXITCODE) { throw 'Compiled component/source validation failed.' }
    if ($Integration) {
        docker exec $container python3 /repo/scripts/cpm/integration_short.py --baseline
        if ($LASTEXITCODE) { throw 'Original component baseline failed.' }
        docker exec $container python3 /repo/scripts/cpm/integration_short.py
        if ($LASTEXITCODE) { throw 'Patched component integration failed.' }
        & C:\Python38\python.exe scripts/cpm/summarize.py
        if ($LASTEXITCODE) { throw 'Evidence summary failed.' }
    }
} finally { Pop-Location }
