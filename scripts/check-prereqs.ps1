# PowerShell shim that dispatches to scripts/check_prereqs.py.
# Verifies a Python interpreter is on PATH first; otherwise prints a clear
# install hint and exits non-zero before attempting to invoke the .py script.
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyScript = Join-Path $ScriptDir 'check_prereqs.py'

$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}

if (-not $PythonCmd) {
    Write-Error "No python interpreter on PATH. Install Python 3.13+ from https://python.org (or 'winget install Python.Python.3.13') and rerun."
    exit 1
}

& $PythonCmd.Source $PyScript @Args
exit $LASTEXITCODE
