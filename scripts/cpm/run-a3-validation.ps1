param([string]$Case = ('a3-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if ($Case -notmatch '^a3-[a-zA-Z0-9_-]+$') { throw 'Invalid case name.' }
Push-Location $root
$container = 'exfmd-cpm-a3'
$wasRunning = $true
try {
    if ((git branch --show-current) -ne 'a3-temporal-plausibility') { throw 'Expected a3-temporal-plausibility branch.' }
    $path = Join-Path $root "results/phase3/$Case"
    if (Test-Path -LiteralPath $path) { throw 'Case already exists; evidence is never overwritten.' }
    New-Item -ItemType Directory -Path $path | Out-Null
    git status --porcelain=v1 | Set-Content -LiteralPath "$path/git-status-before.txt"
    git log -5 --format=fuller | Set-Content -LiteralPath "$path/git-log-before.txt"
    docker ps -a --no-trunc --format '{{json .}}' | Set-Content -LiteralPath "$path/containers-before.jsonl"
    $image = docker image inspect sarra13ba/exfmd-artery:1.0 --format '{{.Id}}'
    if ($LASTEXITCODE -or $image -ne 'sha256:333eddecf31deda29368a7512074dc959ece026155ced270ebb763c1278fb511') { throw 'Expected local original image; no pull or image rebuild is performed.' }
    $image | Set-Content -LiteralPath "$path/image-before.txt"
    $names = @(docker ps -a --format '{{.Names}}')
    if ($container -notin $names) {
        docker create --name $container --network none --cpus 2 --memory 4g --mount "type=bind,source=$root,target=/repo,readonly" --mount "type=bind,source=$root\results\phase3,target=/evidence" sarra13ba/exfmd-artery:1.0 sleep infinity | Out-Null
        if ($LASTEXITCODE) { throw 'Cannot create isolated builder.' }
    }
    $config = @(docker inspect $container | ConvertFrom-Json)[0]
    if ($config.Image -ne $image -or $config.HostConfig.NetworkMode -ne 'none') { throw 'Unexpected builder image/network.' }
    $repoMount = @($config.Mounts | Where-Object { $_.Destination -eq '/repo' })
    $evidenceMount = @($config.Mounts | Where-Object { $_.Destination -eq '/evidence' })
    if ($repoMount.Count -ne 1 -or $repoMount[0].RW -or $repoMount[0].Source -ne $root -or $evidenceMount.Count -ne 1 -or $evidenceMount[0].Source -ne "$root\results\phase3") { throw 'Unexpected builder mounts.' }
    $wasRunning = $config.State.Running
    python scripts/cpm/a3_preserve.py "results/phase3/$Case" before
    if ($LASTEXITCODE) { throw 'Cannot fingerprint previous evidence.' }
    if (-not $wasRunning) { docker start $container | Out-Null; if ($LASTEXITCODE) { throw 'Cannot start isolated builder.' } }
    foreach ($script in @('a3_build.py','a3_recorded.py','a3_native.py','a3_verify_native.py','a3_finalize.py')) {
        docker exec -e "EXFMD_A3_CASE=/evidence/$Case" $container python3 "/repo/scripts/cpm/$script" 2>&1 | Tee-Object -FilePath "$path/$script.log"
        if ($LASTEXITCODE) { throw "$script failed; stop before any subsequent test." }
    }
    python scripts/cpm/a3_preserve.py "results/phase3/$Case" after
    if ($LASTEXITCODE) { throw 'Prior evidence preservation failed.' }
    docker image inspect sarra13ba/exfmd-artery:1.0 --format '{{.Id}}' | Set-Content -LiteralPath "$path/image-after.txt"
    Write-Output "A3 evidence: $path"
} finally {
    if (-not $wasRunning) { docker stop $container | Out-Null }
    if ($path -and (Test-Path -LiteralPath $path)) { docker ps -a --no-trunc --format '{{json .}}' | Set-Content -LiteralPath "$path/containers-after.jsonl" }
    Pop-Location
}
