$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot "dev-backend.ps1"
$frontendScript = Join-Path $PSScriptRoot "dev-frontend.ps1"

Write-Host "Starting StockLLM backend and frontend..."
$backend = Start-Job -Name "stockllm-dev-backend" -ScriptBlock {
    param($ScriptPath, $WorkingDirectory)
    Set-Location $WorkingDirectory
    & $ScriptPath
} -ArgumentList $backendScript, $root

try {
    & $frontendScript
}
finally {
    Stop-Job $backend -ErrorAction SilentlyContinue
    Remove-Job $backend -Force -ErrorAction SilentlyContinue
}
