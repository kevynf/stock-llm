$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Missing .venv. Run .\scripts\bootstrap.ps1 first."
}

$portText = if ($env:STOCKLLM_DEV_BACKEND_PORT) { $env:STOCKLLM_DEV_BACKEND_PORT } else { "8768" }
$port = 0
if (-not [int]::TryParse($portText, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
    throw "STOCKLLM_DEV_BACKEND_PORT must be a valid TCP port."
}

function Test-LocalPort([int]$Port) {
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.ConnectAsync("127.0.0.1", $Port)
        return $pending.Wait(500) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

if (Test-LocalPort $port) {
    $origin = "http://127.0.0.1:$port"
    try {
        $health = Invoke-RestMethod "$origin/api/v1/health" -TimeoutSec 2
        $required = @("desktop-session-token", "selection-events", "system-diagnostics")
        $missing = @($required | Where-Object { $_ -notin @($health.capabilities) })
        if ($health.status -eq "ok" -and $health.protocol_version -eq 1 -and $missing.Count -eq 0) {
            Write-Host "Compatible StockLLM backend is already running at $origin."
            exit 0
        }
        throw "The service has an incompatible StockLLM health contract."
    }
    catch {
        throw "Port $port is occupied, but no compatible StockLLM backend responded. Choose another port with STOCKLLM_DEV_BACKEND_PORT. $($_.Exception.Message)"
    }
}

Set-Location $root
& $venvPython -m uvicorn stockllm.main:app --app-dir backend --host 127.0.0.1 --port $port --reload --reload-dir backend
