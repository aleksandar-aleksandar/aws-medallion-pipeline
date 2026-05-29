param(
    [Parameter(Mandatory = $true)]
    [string]$DatasetName,

    [Parameter(Mandatory = $true)]
    [string]$LocalFile,

    [string]$TerraformDir = "infrastructure\terraform"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Test-Path $LocalFile)) {
    throw "File not found: $LocalFile"
}

$terraform = Join-Path $PSScriptRoot "terraform.ps1"
$tfDir = (Resolve-Path (Join-Path $repoRoot $TerraformDir)).Path
$bucket = & $terraform -chdir="$tfDir" output -raw data_lake_bucket_name
$fileName = Split-Path -Leaf $LocalFile
$s3Key = "bronze/x/dataset=$DatasetName/raw/$fileName"

Write-Host "Uploading to s3://$bucket/$s3Key ..."
aws s3 cp $LocalFile "s3://$bucket/$s3Key"

Write-Host "Done. Bronze X path: s3://$bucket/bronze/x/dataset=$DatasetName/"
