param(
    [string]$Scenario = "scenarios/korea_defense_uas_utm_ops.json",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $RepoRoot "src"

python -m uas_utm_service.server `
    --host $HostName `
    --port $Port `
    --scenario (Join-Path $RepoRoot $Scenario)
