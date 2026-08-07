$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Missing .venv. Run .\scripts\bootstrap.ps1 first."
}
$pnpmCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
if (-not $pnpmCommand) { $pnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue }
$pnpmPrefix = @()
if (-not $pnpmCommand) {
    $pnpmCommand = Get-Command corepack -ErrorAction SilentlyContinue
    if (-not $pnpmCommand) { throw "Missing pnpm or Corepack. Install Node.js with Corepack enabled." }
    $pnpmPrefix = @("pnpm")
}
Set-Location $root
$pytestBase = Join-Path $root (".tmp\pytest-" + [guid]::NewGuid().ToString("N"))
& $venvPython -m pytest -p no:cacheprovider --basetemp $pytestBase
if ($LASTEXITCODE -ne 0) { throw "Backend test suite failed." }
Set-Location (Join-Path $root "frontend")
& $pnpmCommand.Path @pnpmPrefix run api:check
if ($LASTEXITCODE -ne 0) { throw "Frontend OpenAPI contract check failed." }
& $pnpmCommand.Path @pnpmPrefix run build
if ($LASTEXITCODE -ne 0) { throw "Frontend production build failed." }
