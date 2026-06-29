param(
    [string]$TerraformDir = "infrastructure\terraform"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$terraform = Join-Path $PSScriptRoot "terraform.ps1"
$tfDir = (Resolve-Path (Join-Path $repoRoot $TerraformDir)).Path
$topicArn = & $terraform -chdir="$tfDir" output -raw pipeline_alerts_topic_arn 2>$null
if (-not $topicArn) {
    throw "pipeline_alerts_topic_arn not found. Set discord_webhook_url in terraform.tfvars and run terraform apply."
}

$messageFile = Join-Path $env:TEMP "discord-test-alarm.json"
$messageJson = @'
{
  "AlarmName": "social-medias-dev-test-alarm",
  "NewStateValue": "ALARM",
  "NewStateReason": "Manual test from test_discord_notify.ps1",
  "StateChangeTime": "2026-06-28T14:00:00.0000000Z",
  "Trigger": {
    "Dimensions": [
      { "name": "FunctionName", "value": "social-medias-dev-test" }
    ]
  }
}
'@
[System.IO.File]::WriteAllText($messageFile, $messageJson, [System.Text.UTF8Encoding]::new($false))

aws sns publish --topic-arn $topicArn --message "file://$messageFile"
Write-Host "Test alert published to SNS. Check your Discord channel."
