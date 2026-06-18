param(
    [string]$Scenario = "scenarios/normal_utm_ops.json",
    [string]$Output = "output/uas_utm_summary.json",
    [string]$TelemetryOutput = "output/uas_utm_telemetry.jsonl"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $RepoRoot "src"

python -m uas_utm.cli `
    --scenario (Join-Path $RepoRoot $Scenario) `
    --output (Join-Path $RepoRoot $Output) `
    --telemetry-output (Join-Path $RepoRoot $TelemetryOutput)

Write-Host "summary: $Output"
Write-Host "telemetry: $TelemetryOutput"
