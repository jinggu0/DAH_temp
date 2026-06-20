param(
    [string]$Scenario = "scenarios/korea_defense_uas_utm_ops.json",
    [string]$ListenHost = "0.0.0.0",
    [int]$ListenPort = 14550,
    [string]$IngestUrl = "http://127.0.0.1:8080/api/telemetry/ingest"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $RepoRoot "src"

python -m uas_utm_gateway.udp_gateway `
    --listen-host $ListenHost `
    --listen-port $ListenPort `
    --scenario (Join-Path $RepoRoot $Scenario) `
    --ingest-url $IngestUrl
