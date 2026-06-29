param(
    [string]$MetricDate = "",
    [string]$TerraformDir = "infrastructure\terraform"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$terraform = Join-Path $PSScriptRoot "terraform.ps1"
$tfDir = (Resolve-Path (Join-Path $repoRoot $TerraformDir)).Path
$lambdaName = & $terraform -chdir="$tfDir" output -raw gold_transform_lambda_name
if (-not $lambdaName) {
    throw "Could not read gold_transform_lambda_name. Run terraform apply first."
}

$payload = @{}
if ($MetricDate) {
    $payload.metric_date = $MetricDate
}
$payloadJson = if ($payload.Count -eq 0) { "{}" } else { $payload | ConvertTo-Json -Compress }

$payloadFile = Join-Path $env:TEMP "gold-payload.json"
[System.IO.File]::WriteAllText($payloadFile, $payloadJson, [System.Text.UTF8Encoding]::new($false))

Write-Host "Invoking $lambdaName ..."
aws lambda invoke `
    --function-name $lambdaName `
    --cli-read-timeout 900 `
    --payload "file://$payloadFile" `
    --cli-binary-format raw-in-base64-out `
  (Join-Path $env:TEMP "gold-response.json")

Get-Content (Join-Path $env:TEMP "gold-response.json")
Write-Host "`nCheck CloudWatch Logs: /aws/lambda/$lambdaName"

$bucket = & $terraform -chdir="$tfDir" output -raw data_lake_bucket_name
Write-Host "Gold output: s3://$bucket/gold/"
