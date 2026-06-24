param(
    [string]$Scenario = "scenarios/korea_defense_uas_utm_ops.json",
    [string]$ServiceUrl = "http://127.0.0.1:8080",
    [string]$HostName = "0.0.0.0",
    [int]$Port = 14551,
    [string]$SigningKeyHex = "",
    [int]$SigningLinkId = 0
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $RepoRoot "src"

$argsList = @(
    "-m", "uas_utm_gateway.bidirectional_gateway",
    "--listen-host", $HostName,
    "--listen-port", $Port,
    "--scenario", (Join-Path $RepoRoot $Scenario),
    "--service-url", $ServiceUrl
)

if ($SigningKeyHex) {
    $argsList += @("--signing-key-hex", $SigningKeyHex, "--signing-link-id", $SigningLinkId)
}

python @argsList