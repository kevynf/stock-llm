[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [string]$PythonPath
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TargetTriple = "x86_64-pc-windows-msvc"
$TauriConfig = Get-Content (Join-Path $ProjectRoot "src-tauri\tauri.conf.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$AppVersion = $TauriConfig.version
$Python = if ($PythonPath) { $PythonPath } else { Join-Path $ProjectRoot ".venv\Scripts\python.exe" }
$UserCargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if ((Test-Path -LiteralPath $UserCargoBin) -and -not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    $env:Path = "$UserCargoBin;$env:Path"
}

function Require-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) { throw "Missing $Name. $Hint" }
}

Require-Command "pnpm" "Install Node.js and pnpm first."
Require-Command "cargo" "Install Rust stable and the $TargetTriple target."
Require-Command "rustc" "Install Rust stable and the $TargetTriple target."
if (-not (Test-Path -LiteralPath $Python)) { throw "Project virtual environment not found: $Python. Run scripts/bootstrap.ps1 first." }
$PythonVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($PythonVersion -ne "3.12") { throw "Desktop builds require Python 3.12; found $PythonVersion at $Python." }

$VsWhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path -LiteralPath $VsWhere)) { throw "Visual Studio Build Tools not found. Install the Desktop development with C++ workload." }
$VsPath = & $VsWhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $VsPath) { throw "MSVC x64 tools not found. Install the Desktop development with C++ workload." }

Push-Location $ProjectRoot
try {
    if (-not $SkipInstall) {
        pnpm install --frozen-lockfile
        & $Python -m pip install -e ".[data,desktop]"
    }
    pnpm --dir frontend run build
    & $Python -m PyInstaller --clean --noconfirm packaging\stockllm-backend.spec

    $BinaryDirectory = Join-Path $ProjectRoot "src-tauri\binaries"
    New-Item -ItemType Directory -Force -Path $BinaryDirectory | Out-Null
    $SidecarSource = Join-Path $ProjectRoot "dist\stockllm-backend.exe"
    if (-not (Test-Path -LiteralPath $SidecarSource)) { throw "PyInstaller sidecar not found: $SidecarSource" }
    Copy-Item -LiteralPath $SidecarSource -Destination (Join-Path $BinaryDirectory "stockllm-backend-$TargetTriple.exe") -Force

    if (Get-Command rustup -ErrorAction SilentlyContinue) { rustup target add $TargetTriple }
    & (Join-Path $ProjectRoot "frontend\node_modules\.bin\tauri.CMD") build --target $TargetTriple

    $Installer = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "src-tauri\target") -Recurse -Filter "*setup.exe" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $Installer) { throw "Tauri completed without producing an NSIS installer." }
    $OutputDirectory = Join-Path $ProjectRoot "packaging\dist"
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $Output = Join-Path $OutputDirectory "StockLLM_${AppVersion}_x64-setup.exe"
    Copy-Item -LiteralPath $Installer.FullName -Destination $Output -Force
    Write-Host "Installer created: $Output"
}
finally { Pop-Location }
