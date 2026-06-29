param(
    [string]$ContentDate = "",
    [switch]$NoX,
    [string]$TerraformDir = "infrastructure\terraform"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$terraform = Join-Path $PSScriptRoot "terraform.ps1"
$tfDir = (Resolve-Path (Join-Path $repoRoot $TerraformDir)).Path
$lambdaName = & $terraform -chdir="$tfDir" output -raw silver_normalize_lambda_name
if (-not $lambdaName) {
    throw "Could not read silver_normalize_lambda_name. Run terraform apply first."
}

$payload = @{ process_x = (-not $NoX) }
if ($ContentDate) {
    $payload.content_date = $ContentDate
}
$payloadJson = $payload | ConvertTo-Json -Compress

$payloadFile = Join-Path $env:TEMP "silver-payload.json"
[System.IO.File]::WriteAllText($payloadFile, $payloadJson, [System.Text.UTF8Encoding]::new($false))

Write-Host "Invoking $lambdaName ..."
aws lambda invoke `
    --function-name $lambdaName `
    --payload "file://$payloadFile" `
    --cli-binary-format raw-in-base64-out `
  (Join-Path $env:TEMP "silver-response.json")

Get-Content (Join-Path $env:TEMP "silver-response.json")
Write-Host "`nCheck CloudWatch Logs: /aws/lambda/$lambdaName"

$bucket = & $terraform -chdir="$tfDir" output -raw data_lake_bucket_name
Write-Host "Silver output: s3://$bucket/silver/"
