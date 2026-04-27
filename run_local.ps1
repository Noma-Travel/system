param(
    [string]$AwsProfile = "noma",
    [string]$AwsRegion = "us-east-1"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "Virtual environment not found at .\venv" -ForegroundColor Yellow
    Write-Host "Create it first with: py -3.12 -m venv venv" -ForegroundColor Yellow
    exit 1
}

$env:AWS_PROFILE = $AwsProfile
$env:AWS_DEFAULT_REGION = $AwsRegion

# Always prioritize local dev sources over site-packages wheels.
$repoRoot = Split-Path -Parent $scriptDir
$devApiPath = Join-Path $repoRoot "dev\\renglo-api"
$devLibPath = Join-Path $repoRoot "dev\\renglo-lib"
if ((Test-Path $devApiPath) -and (Test-Path $devLibPath)) {
    if ($env:PYTHONPATH) {
        $env:PYTHONPATH = "$devApiPath;$devLibPath;$env:PYTHONPATH"
    } else {
        $env:PYTHONPATH = "$devApiPath;$devLibPath"
    }
}

Write-Host "Starting local backend with AWS profile '$AwsProfile' in region '$AwsRegion'..." -ForegroundColor Cyan
Write-Host "Backend URL: http://127.0.0.1:5001" -ForegroundColor Cyan

& ".\venv\Scripts\python.exe" ".\main.py"
