param([string]$Case = ('qualification-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if ($Case -notmatch '^qualification-[a-zA-Z0-9_-]+$') { throw 'Invalid case name.' }
Push-Location $root
$container='exfmd-cpm-a3'; $wasRunning=$true
$calibrationBuild='/repo/results/phase3/calibration-20261108-190113/build'
function Invoke-QualificationStep([string]$Script,[string]$Log,[hashtable]$Variables=@{}) {
    $dockerArgs=@('exec','-e',"EXFMD_A3_CASE=/evidence/$Case",'-e',"EXFMD_A3_REPLAY_BUILD=$calibrationBuild")
    foreach($key in $Variables.Keys){$dockerArgs+=@('-e',"$key=$($Variables[$key])")}
    $dockerArgs+=@($container,'python3',"/repo/scripts/cpm/$Script")
    docker @dockerArgs 2>&1|Tee-Object -FilePath "$path/$Log"
    if($LASTEXITCODE){throw "$Script failed; no subsequent step is executed."}
}
try {
    if((git branch --show-current) -ne 'a3-temporal-plausibility'){throw 'Expected a3-temporal-plausibility.'}
    $path=Join-Path $root "results/phase3/$Case"
    if(Test-Path -LiteralPath $path){throw 'Existing evidence folder cannot be reused.'}
    New-Item -ItemType Directory -Path "$path/before-sources"|Out-Null
    git status --porcelain=v1|Set-Content -LiteralPath "$path/git-before.txt"
    docker ps -a --no-trunc --format '{{json .}}'|Set-Content -LiteralPath "$path/containers-before.jsonl"
    $config=@(docker inspect $container|ConvertFrom-Json)[0]
    if($LASTEXITCODE -or $config.Image -ne 'sha256:333eddecf31deda29368a7512074dc959ece026155ced270ebb763c1278fb511' -or $config.HostConfig.NetworkMode -ne 'none'){throw 'Existing isolated A3 builder required.'}
    $repoMount=@($config.Mounts|Where-Object{$_.Destination -eq '/repo'})
    $evidenceMount=@($config.Mounts|Where-Object{$_.Destination -eq '/evidence'})
    if($repoMount.Count -ne 1 -or $repoMount[0].RW -or $repoMount[0].Source -ne $root -or $evidenceMount.Count -ne 1 -or $evidenceMount[0].Source -ne "$root\results\phase3"){throw 'Unexpected builder mounts.'}
    $wasRunning=$config.State.Running
    foreach($name in @('fusion_detector.py','perception_contract.py')){
        Copy-Item -LiteralPath "results/phase1/a1-e2e-20261106-161848/attempt-02/sources/cosimulation/carla_multi_agent/$name" -Destination "$path/before-sources/$name"
    }
    python scripts/cpm/calibration_preserve.py "results/phase3/$Case" before
    if($LASTEXITCODE){throw 'Cannot fingerprint old evidence.'}
    python scripts/cpm/qualification_python_tests.py "results/phase3/$Case/python-tests-02"
    if($LASTEXITCODE){throw 'Python tests failed.'}
    python scripts/cpm/qualification_replay.py --case "results/phase3/$Case" --label analysis-validated
    if($LASTEXITCODE){throw 'Paired perception replay failed.'}
    if(-not $wasRunning){docker start $container|Out-Null;if($LASTEXITCODE){throw 'Cannot start isolated builder.'}}
    Invoke-QualificationStep 'qualification_cpp.py' 'cpp-tests.log'
    Invoke-QualificationStep 'a3_native.py' 'native.log' @{EXFMD_A3_NED_POLICY="/evidence/$Case/policy-selected.json";EXFMD_A3_WALL_TIMEOUT='120'}
    Invoke-QualificationStep 'a3_verify_native.py' 'verify-native.log'
    Invoke-QualificationStep 'qualification_finalize.py' 'finalize.log'
    python scripts/cpm/calibration_preserve.py "results/phase3/$Case" after
    if($LASTEXITCODE){throw 'Old evidence changed.'}
    Write-Output "A3.3 evidence: $path"
} finally {
    if(-not $wasRunning){docker stop $container|Out-Null}
    if($path -and (Test-Path -LiteralPath $path)){docker ps -a --no-trunc --format '{{json .}}'|Set-Content -LiteralPath "$path/containers-after.jsonl"}
    Pop-Location
}
