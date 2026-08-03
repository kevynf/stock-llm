param(
    [string]$PyPiIndex = "https://pypi.tuna.tsinghua.edu.cn/simple",
    [string]$NpmRegistry = "https://registry.npmmirror.com"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$pipCache = Join-Path $projectRoot ".pip-cache"

Set-Location $projectRoot

if (-not (Test-Path $venvPython)) {
    python -m venv $venvPath
}

$env:PIP_CACHE_DIR = $pipCache
& $venvPython -m pip install --index-url $PyPiIndex -e ".[dev,data]"
pnpm.cmd install --registry $NpmRegistry --store-dir (Join-Path $projectRoot ".pnpm-store")

Write-Host "Dependencies are isolated in .venv, node_modules, .pip-cache, and .pnpm-store."
