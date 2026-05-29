param(
    [string]$ContentDate = "",
    [string]$TerraformDir = "infrastructure\terraform"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$terraform = Join-Path $PSScriptRoot "terraform.ps1"
$tfDir = (Resolve-Path (Join-Path $repoRoot $TerraformDir)).Path
$lambdaName = & $terraform -chdir="$tfDir" output -raw hn_bronze_lambda_name
if (-not $lambdaName) {
    throw "Could not read hn_bronze_lambda_name. Run terraform apply first."
}

$payload = "{}"
if ($ContentDate) {
    $payload = (@{ content_date = $ContentDate } | ConvertTo-Json -Compress)
}

$payloadFile = Join-Path $env:TEMP "hn-bronze-payload.json"
# UTF-8 without BOM — PowerShell's default utf8 adds BOM and breaks Lambda JSON parsing
[System.IO.File]::WriteAllText($payloadFile, $payload, [System.Text.UTF8Encoding]::new($false))

Write-Host "Invoking $lambdaName ..."
aws lambda invoke `
    --function-name $lambdaName `
    --payload "file://$payloadFile" `
    --cli-binary-format raw-in-base64-out `
  (Join-Path $env:TEMP "hn-bronze-response.json")

Get-Content (Join-Path $env:TEMP "hn-bronze-response.json")
Write-Host "`nCheck CloudWatch Logs: /aws/lambda/$lambdaName"
