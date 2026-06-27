param(
  [string]$Scenario = "scenarios/korea_defense_uas_utm_ops.json",
  [string]$ServiceUrl = "http://127.0.0.1:8080",
  [string]$GatewayHost = "127.0.0.1",
  [int]$GatewayPort = 14551,
  [string]$AssetId = "small-dronebot-01"
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"
python -m uas_utm_gateway.mock_smoke_test --scenario $Scenario --service-url $ServiceUrl --gateway-host $GatewayHost --gateway-port $GatewayPort --asset-id $AssetId
