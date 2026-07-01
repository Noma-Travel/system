# Wrapper for: python scripts/run.py @args
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)
$ErrorActionPreference = "Stop"
$systemRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $systemRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}
& $python (Join-Path $PSScriptRoot "run.py") @Args
