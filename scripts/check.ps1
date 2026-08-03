$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Missing .venv. Run .\scripts\bootstrap.ps1 first."
}
Set-Location $root
& $venvPython -m pytest
Set-Location (Join-Path $root "frontend")
pnpm.cmd run build
