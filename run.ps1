# Noma dev launcher — use instead of alias when `run` is not in PATH
# Usage: .\run.ps1 noma console backend env:staging handler:local
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)
$ErrorActionPreference = "Stop"
$systemRoot = $PSScriptRoot
$python = Join-Path $systemRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}
& $python (Join-Path $systemRoot "scripts\run.py") @Args
