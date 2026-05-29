# Wrapper so Terraform works even if PATH wasn't refreshed in this terminal.
$tfCandidates = @(
    "$env:USERPROFILE\Downloads\terraform_1.15.5_windows_amd64\terraform.exe",
    "C:\terraform\terraform_1.15.5_windows_amd64\terraform.exe"
)

$terraformExe = $null
foreach ($path in $tfCandidates) {
    if (Test-Path $path) {
        $terraformExe = $path
        break
    }
}

if (-not $terraformExe) {
    $terraformExe = (Get-Command terraform -ErrorAction SilentlyContinue).Source
}

if (-not $terraformExe) {
    Write-Error @"
terraform.exe not found. Either:
  1. Add Terraform folder to PATH and restart Cursor completely, or
  2. Set env var TERRAFORM_EXE to full path of terraform.exe
"@
    exit 1
}

if ($env:TERRAFORM_EXE) {
    $terraformExe = $env:TERRAFORM_EXE
}

& $terraformExe @args
exit $LASTEXITCODE
