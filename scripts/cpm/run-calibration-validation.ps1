param([string]$Case = ('calibration-' + (Get-Date -Format 'yyyyMMdd-HHmmss')))
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if ($Case -notmatch '^calibration-[a-zA-Z0-9_-]+$') { throw 'Invalid case name.' }
Push-Location $root
$container = 'exfmd-cpm-a3'
$wasRunning = $true
function Invoke-CalibrationStep([string]$Script, [string]$Log, [hashtable]$Variables = @{}) {
    $dockerArgs = @('exec', '-e', "EXFMD_A3_CASE=/evidence/$Case")
    foreach ($key in $Variables.Keys) { $dockerArgs += @('-e', "$key=$($Variables[$key])") }
    $dockerArgs += @($container, 'python3', "/repo/scripts/cpm/$Script")
    docker @dockerArgs 2>&1 | Tee-Object -FilePath "$path/$Log"
    if ($LASTEXITCODE) { throw "$Script failed; subsequent steps are stopped." }
}
try {
    if ((git branch --show-current) -ne 'a3-temporal-plausibility') { throw 'Expected a3-temporal-plausibility.' }
    $path = Join-Path $root "results/phase3/$Case"
    if (Test-Path -LiteralPath $path) { throw 'Existing evidence folder is never reused.' }
    New-Item -ItemType Directory -Path $path | Out-Null
    git status --porcelain=v1 | Set-Content -LiteralPath "$path/git-before.txt"
    docker ps -a --no-trunc --format '{{json .}}' | Set-Content -LiteralPath "$path/containers-before.jsonl"
    $config = @(docker inspect $container | ConvertFrom-Json)[0]
    if ($LASTEXITCODE -or $config.Image -ne 'sha256:333eddecf31deda29368a7512074dc959ece026155ced270ebb763c1278fb511' -or $config.HostConfig.NetworkMode -ne 'none') { throw 'Prepared isolated A3 builder required; no pull/rebuild is performed.' }
    $repoMount = @($config.Mounts | Where-Object { $_.Destination -eq '/repo' })
    $evidenceMount = @($config.Mounts | Where-Object { $_.Destination -eq '/evidence' })
    if ($repoMount.Count -ne 1 -or $repoMount[0].RW -or $repoMount[0].Source -ne $root -or $evidenceMount.Count -ne 1 -or $evidenceMount[0].Source -ne "$root\results\phase3") { throw 'Unexpected builder mounts.' }
    $wasRunning = $config.State.Running
    python scripts/cpm/calibration_preserve.py "results/phase3/$Case" before
    if ($LASTEXITCODE) { throw 'Cannot fingerprint old evidence.' }
    python scripts/cpm/calibration_analyze.py --case "results/phase3/$Case" --label analysis-final
    if ($LASTEXITCODE) { throw 'Frame/tracker evidence join failed.' }
    if (-not $wasRunning) { docker start $container | Out-Null; if ($LASTEXITCODE) { throw 'Cannot start builder.' } }
    Invoke-CalibrationStep 'calibration_sweep.py' 'sweep-before.log'
    Invoke-CalibrationStep 'a3_build.py' 'build.log' @{EXFMD_CALIBRATION_TESTS='1'}
    Invoke-CalibrationStep 'a3_recorded.py' 'recorded.log'
    Invoke-CalibrationStep 'calibration_sweep.py' 'sweep-after.log' @{EXFMD_CALIBRATION_STAGE='after'}
    $baseline = @{acceleration_m_s2=1.6;deceleration_m_s2=4.6;angular_rate_deg_s=90;excess_speed_m_s=3}
    $selected = @{acceleration_m_s2=3;deceleration_m_s2=4.5;angular_rate_deg_s=90;excess_speed_m_s=3}
    $baseline | ConvertTo-Json | Set-Content -Encoding Ascii -LiteralPath "$path/policy-baseline.json"
    $selected | ConvertTo-Json | Set-Content -Encoding Ascii -LiteralPath "$path/policy-selected.json"
    Invoke-CalibrationStep 'a3_native.py' 'native-baseline.log' @{EXFMD_A3_NED_POLICY="/evidence/$Case/policy-baseline.json"}
    Invoke-CalibrationStep 'a3_verify_native.py' 'verify-baseline.log'
    Invoke-CalibrationStep 'a3_native.py' 'native-selected.log' @{EXFMD_A3_NED_POLICY="/evidence/$Case/policy-selected.json"}
    Invoke-CalibrationStep 'a3_verify_native.py' 'verify-selected.log'
    Invoke-CalibrationStep 'a3_finalize.py' 'finalize.log'
    Invoke-CalibrationStep 'calibration_summary.py' 'summary.log'
    python scripts/cpm/calibration_preserve.py "results/phase3/$Case" after
    if ($LASTEXITCODE) { throw 'Old evidence changed.' }
    Write-Output "Calibration evidence: $path"
} finally {
    if (-not $wasRunning) { docker stop $container | Out-Null }
    if ($path -and (Test-Path -LiteralPath $path)) { docker ps -a --no-trunc --format '{{json .}}' | Set-Content -LiteralPath "$path/containers-after.jsonl" }
    Pop-Location
}
