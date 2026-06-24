param(
    [string]$ServiceUrl = "http://127.0.0.1:8080",
    [string]$EdgeId = "edge-dronebot-01",
    [string]$DeviceType = "uav_edge",
    [string]$Asset = "small-dronebot-01",
    [switch]$Once,
    [switch]$EmitSampleTelemetry
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $RepoRoot "src"

$argsList = @(
    "-m", "uas_utm_edge.agent",
    "--service-url", $ServiceUrl,
    "--edge-id", $EdgeId,
    "--device-type", $DeviceType,
    "--asset", $Asset
)
if ($Once) { $argsList += "--once" }
if ($EmitSampleTelemetry) { $argsList += "--emit-sample-telemetry" }

python @argsList
