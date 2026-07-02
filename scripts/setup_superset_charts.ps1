param(
    [string]$TerraformDir = "infrastructure\terraform"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# X tweets are in 2023; gold must include those dates for X active users > 0.
$xDates = @("2023-02-26", "2023-02-27", "2023-02-28", "2023-03-01")
Write-Host "Computing gold metrics for X tweet dates ..."
foreach ($d in $xDates) {
    Write-Host "  gold transform: $d"
    & (Join-Path $PSScriptRoot "invoke_gold.ps1") -MetricDate $d -TerraformDir $TerraformDir
}

Write-Host "`nLoading gold data into Postgres ..."
& (Join-Path $PSScriptRoot "invoke_gold_load.ps1") -TerraformDir $TerraformDir

Write-Host "`nCreating/updating Superset datasets and charts ..."
$python = @(
    (Join-Path $env:LOCALAPPDATA "Python\bin\python.exe"),
    "py",
    "python"
) | Where-Object { $_ -eq "py" -or $_ -eq "python" -or (Test-Path $_) } | Select-Object -First 1

if (-not $python) {
    throw "Python not found. Install Python 3 or add it to PATH."
}

& $python (Join-Path $PSScriptRoot "setup_superset_charts.py") `
    --terraform-dir (Resolve-Path (Join-Path $repoRoot $TerraformDir)).Path `
    --update
