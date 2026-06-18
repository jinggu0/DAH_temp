param(
    [string]$Scenario = "scenarios/uav_ugv_convoy.json",
    [string]$Output = "output/harness_summary.json"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ScenarioPath = Join-Path $RepoRoot $Scenario
$OutputPath = Join-Path $RepoRoot $Output
$OutputDir = Split-Path -Parent $OutputPath

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$env:PYTHONPATH = Join-Path $RepoRoot "src"

python -m dah_harness.cli `
    --scenario $ScenarioPath `
    --output $OutputPath

Write-Host "summary: $OutputPath"
