param([string]$Case = ('stabilite-a34-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if($Case -notmatch '^stabilite-a34-[a-zA-Z0-9_-]+$'){throw 'Invalid case name.'}
Push-Location $root
$wasRunning=$true; $builder='exfmd-cpm-a3'
try {
    if((git branch --show-current) -ne 'a3-temporal-plausibility'){throw 'Expected a3-temporal-plausibility.'}
    $path=Join-Path $root "results/phase3/$Case"
    if(Test-Path -LiteralPath $path){throw 'Existing evidence folder cannot be overwritten.'}
    New-Item -ItemType Directory -Path "$path/offline-client"|Out-Null
    git status --porcelain=v1|Set-Content -LiteralPath "$path/git-before.txt"
    docker ps -a --no-trunc --format '{{json .}}'|Set-Content -LiteralPath "$path/containers-before.jsonl"
    $rosImage=docker image inspect sarra13ba/exfmd-ros:1.0 --format '{{.Id}}'
    if($LASTEXITCODE -or $rosImage -ne 'sha256:dd5e867a47d30a1e6f73311c14b41606623d0574d7df94fa49da5a4da9020a08'){throw 'Expected existing ROS tool image; no image pull/rebuild.'}
    $config=@(docker inspect $builder|ConvertFrom-Json)[0]
    if($LASTEXITCODE -or $config.Image -ne 'sha256:333eddecf31deda29368a7512074dc959ece026155ced270ebb763c1278fb511' -or $config.HostConfig.NetworkMode -ne 'none'){throw 'Expected existing isolated Artery builder.'}
    $repoMount=@($config.Mounts|Where-Object{$_.Destination -eq '/repo'})
    $evidenceMount=@($config.Mounts|Where-Object{$_.Destination -eq '/evidence'})
    if($repoMount.Count -ne 1 -or $repoMount[0].RW -or $repoMount[0].Source -ne $root -or $evidenceMount.Count -ne 1 -or $evidenceMount[0].Source -ne "$root\results\phase3"){throw 'Unexpected mounts.'}
    $wasRunning=$config.State.Running
    python scripts/cpm/calibration_preserve.py "results/phase3/$Case" before
    if($LASTEXITCODE){throw 'Cannot fingerprint old evidence.'}
    python scripts/cpm/a34_tests.py "results/phase3/$Case/tests"
    if($LASTEXITCODE){throw 'Python regression tests failed.'}
    python scripts/cpm/stability_a34.py --case "results/phase3/$Case" --label analysis-validated
    if($LASTEXITCODE){throw 'Archived/synthetic filter comparison failed.'}
    # Read an existing client SDK from the stopped ROS container. No ROS command
    # or server connection: the tool below only calls carla.Map locally.
    foreach($package in @('carla','carla.libs')){
        docker cp "exfmd-ros:/tmp/exfmd-python/$package" "$path/offline-client/$package"
        if($LASTEXITCODE){throw 'Existing CARLA client SDK/bundled libraries unavailable.'}
    }
    $tool="exfmd-a34-map-$Case"
    docker create --name $tool --network none --cpus 2 --memory 2g --entrypoint python3 --mount "type=bind,source=$root,target=/repo,readonly" --mount "type=bind,source=$root\results\phase3,target=/evidence" -e "EXFMD_A34_CASE=/evidence/$Case" -e "PYTHONPATH=/evidence/$Case/offline-client" sarra13ba/exfmd-ros:1.0 /repo/scripts/cpm/a34_offline_map.py|Out-Null
    if($LASTEXITCODE){throw 'Cannot create offline projection tool.'}
    docker start -a $tool 2>&1|Tee-Object -FilePath "$path/offline-map.log"
    if($LASTEXITCODE){throw 'Projection validation failed; no CPM reconstruction.'}
    python scripts/cpm/a34_cpm_fixtures.py --case "results/phase3/$Case"
    if($LASTEXITCODE){throw 'CPM fixtures failed.'}
    if(-not $wasRunning){docker start $builder|Out-Null;if($LASTEXITCODE){throw 'Builder did not start.'}}
    foreach($script in @('a34_cpp.py','a34_finalize.py')){
        docker exec -e "EXFMD_A34_CASE=/evidence/$Case" $builder python3 "/repo/scripts/cpm/$script" 2>&1|Tee-Object -FilePath "$path/$script.log"
        if($LASTEXITCODE){throw "$script failed; subsequent work stopped."}
    }
    python scripts/cpm/calibration_preserve.py "results/phase3/$Case" after
    if($LASTEXITCODE){throw 'Old evidence changed.'}
    Write-Output "A3.4 evidence: $path"
} finally {
    if(-not $wasRunning){docker stop $builder|Out-Null}
    if($path -and (Test-Path -LiteralPath $path)){docker ps -a --no-trunc --format '{{json .}}'|Set-Content -LiteralPath "$path/containers-after.jsonl"}
    Pop-Location
}
