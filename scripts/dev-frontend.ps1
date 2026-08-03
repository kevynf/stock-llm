$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$port = if ($env:STOCKLLM_DEV_BACKEND_PORT) { $env:STOCKLLM_DEV_BACKEND_PORT } else { "8768" }
if (-not $env:STOCKLLM_DEV_API_URL) {
    $env:STOCKLLM_DEV_API_URL = "http://127.0.0.1:$port"
}
$frontendPort = if ($env:STOCKLLM_DEV_FRONTEND_PORT) { $env:STOCKLLM_DEV_FRONTEND_PORT } else { "5173" }
Write-Host "Vite API proxy: $env:STOCKLLM_DEV_API_URL"
Write-Host "Frontend URL: http://127.0.0.1:$frontendPort"
Set-Location (Join-Path $root "frontend")
if (Get-Command pnpm.cmd -ErrorAction SilentlyContinue) {
    pnpm.cmd run dev
}
elseif (Get-Command npm.cmd -ErrorAction SilentlyContinue) {
    Write-Host "pnpm.cmd was not found; using npm.cmd with the installed dependencies."
    npm.cmd run dev
}
else {
    throw "Neither pnpm.cmd nor npm.cmd was found. Install Node.js 20+ and pnpm 9+."
}
