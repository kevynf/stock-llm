param(
    [string]$PyPiIndex = "https://pypi.tuna.tsinghua.edu.cn/simple",
    [string]$NpmRegistry = "https://registry.npmmirror.com",
    [string]$PythonPath = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$pipCache = Join-Path $projectRoot ".pip-cache"

Set-Location $projectRoot

$pythonVersion = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0) { throw "Unable to run Python at '$PythonPath'." }
if ([version]$pythonVersion -lt [version]"3.12") {
    throw "StockLLM requires Python 3.12 or newer; found $pythonVersion at '$PythonPath'."
}

if (-not (Test-Path $venvPython)) {
    & $PythonPath -m venv $venvPath
}

$venvVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$venvVersion -lt [version]"3.12") {
    throw "Existing project environment requires Python 3.12 or newer; found $venvVersion at '$venvPython'."
}

$env:PIP_CACHE_DIR = $pipCache
& $venvPython -m pip install --index-url $PyPiIndex -e ".[dev,data]"
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
$pnpmCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
if (-not $pnpmCommand) { $pnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue }
$pnpmPrefix = @()
if (-not $pnpmCommand) {
    $pnpmCommand = Get-Command corepack -ErrorAction SilentlyContinue
    if (-not $pnpmCommand) { throw "Missing pnpm or Corepack. Install Node.js with Corepack enabled." }
    $pnpmPrefix = @("pnpm")
}
& $pnpmCommand.Path @pnpmPrefix install --registry $NpmRegistry --store-dir (Join-Path $projectRoot ".pnpm-store")
if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }

Write-Host "Dependencies are isolated in .venv, node_modules, .pip-cache, and .pnpm-store."
