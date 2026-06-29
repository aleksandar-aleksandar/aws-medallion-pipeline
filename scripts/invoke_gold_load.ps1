param(
    [string]$TerraformDir = "infrastructure\terraform"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$terraform = Join-Path $PSScriptRoot "terraform.ps1"
$tfDir = (Resolve-Path (Join-Path $repoRoot $TerraformDir)).Path
$lambdaName = & $terraform -chdir="$tfDir" output -raw gold_to_postgres_lambda_name
if (-not $lambdaName) {
    throw "Could not read gold_to_postgres_lambda_name. Run terraform apply first."
}

$payloadFile = Join-Path $env:TEMP "gold-load-payload.json"
[System.IO.File]::WriteAllText($payloadFile, "{}", [System.Text.UTF8Encoding]::new($false))

Write-Host "Invoking $lambdaName ..."
aws lambda invoke `
    --function-name $lambdaName `
    --cli-read-timeout 600 `
    --payload "file://$payloadFile" `
    --cli-binary-format raw-in-base64-out `
  (Join-Path $env:TEMP "gold-load-response.json")

Get-Content (Join-Path $env:TEMP "gold-load-response.json")
Write-Host "`nSuperset: $(& $terraform -chdir=`"$tfDir`" output -raw superset_url)"
Write-Host "CloudWatch Logs: /aws/lambda/$lambdaName"
