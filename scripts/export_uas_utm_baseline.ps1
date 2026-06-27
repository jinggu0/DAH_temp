param(
    [string]$Scenario = "scenarios/korea_defense_uas_utm_ops.json",
    [string]$OutputDir = "output/baseline",
    [int]$Limit = 500
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $RepoRoot "src"

python -m uas_utm_service.baseline_export `
    --scenario (Join-Path $RepoRoot $Scenario) `
    --output-dir (Join-Path $RepoRoot $OutputDir) `
    --limit $Limit