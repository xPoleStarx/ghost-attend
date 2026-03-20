#Requires -Version 5.1
<#
.SYNOPSIS
  GhostMyShit: finds Python, creates .venv, installs deps, runs the Telegram bot.
  Optional: set GHOST_MYSHIT_PYTHON to full path of python.exe (old: GHOST_ATTEND_PYTHON also supported)
#>
param(
    [switch]$InstallOnly,
    [switch]$SkipInstall,
    [switch]$ForceInstall,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ($SkipInstall -and -not (Test-Path (Join-Path $Root ".venv\Scripts\python.exe"))) {
    Write-Err ".venv missing. Run first: .\Run.ps1 (without -SkipInstall)"
    exit 1
}

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Err($msg) { Write-Host "`n[!] $msg" -ForegroundColor Red }

function Test-ImportsOrExit {
    param([string]$PythonExe)
    # Botun gercek import zinciri (main -> graph -> nodes -> screenshot -> browser_use vb.)
    # Eski kontrol sadece pydantic/langgraph/telegram test ediyordu; eksik browser-use icin yaniltici basari veriyordu.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    Push-Location $Root
    try {
        & $PythonExe -c "from app.agent.task_agent import build_compiled_graph"
        $ec = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    $ErrorActionPreference = $prev
    if ($ec -ne 0) {
        Write-Err "task_agent import failed (exit $ec). See stderr above. Try: Remove-Item -Recurse -Force .venv; .\Run.ps1 -ForceInstall"
        exit 1
    }
}

function Find-SystemPython {
    if ($env:GHOST_MYSHIT_PYTHON) {
        $p = $env:GHOST_MYSHIT_PYTHON.Trim()
        if (Test-Path $p) { return (Resolve-Path $p).Path }
        Write-Err "GHOST_MYSHIT_PYTHON is set but file not found: $p"
    }
    elseif ($env:GHOST_ATTEND_PYTHON) {
        # Backward-compatibility: keep old env var working.
        $p = $env:GHOST_ATTEND_PYTHON.Trim()
        if (Test-Path $p) { return (Resolve-Path $p).Path }
        Write-Err "GHOST_ATTEND_PYTHON is set but file not found: $p"
    }

    foreach ($name in @("python.exe", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -and ($cmd.Source -notmatch "WindowsApps")) {
            return $cmd.Source
        }
    }

    $patterns = @(
        "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
        "${env:ProgramFiles}\Python*\python.exe"
    )
    foreach ($pat in $patterns) {
        $hits = Get-Item $pat -ErrorAction SilentlyContinue | Sort-Object FullName -Descending
        foreach ($h in $hits) {
            if ($h.FullName -notmatch "WindowsApps") { return $h.FullName }
        }
    }

    $dir = "$env:LOCALAPPDATA\Programs\Python"
    if (Test-Path $dir) {
        $deep = Get-ChildItem -Path $dir -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch "WindowsApps" } |
            Select-Object -First 1
        if ($deep) { return $deep.FullName }
    }

    return $null
}

function Ensure-DotEnv {
    if (Test-Path (Join-Path $Root ".env")) { return }
    $ex = Join-Path $Root ".env.example"
    if (-not (Test-Path $ex)) {
        Write-Err ".env missing and .env.example not found."
        exit 1
    }
    Copy-Item $ex (Join-Path $Root ".env")
    Write-Host ""
    Write-Host "Created .env from .env.example - set TELEGRAM_BOT_TOKEN and GOOGLE_API_KEY." -ForegroundColor Yellow
    Write-Host "  notepad `"$Root\.env`"" -ForegroundColor Gray
    Write-Host ""
    if (-not $NonInteractive) {
        $r = Read-Host "Press Enter when done (q to quit)"
        if ($r -eq "q") { exit 1 }
    }
}

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Write-Step "No .venv yet; looking for system Python..."
    $sysPy = Find-SystemPython
    if (-not $sysPy) {
        Write-Host ""
        Write-Host "[!] Python not found. Options:" -ForegroundColor Red
        Write-Host "  - Install Python 3.11+ from https://www.python.org/downloads/ and check Add to PATH"
        Write-Host "  - Or: `$env:GHOST_MYSHIT_PYTHON = 'C:\Path\to\python.exe'  then  .\Run.ps1"
        Write-Host "  - Or: docker compose up --build"
        exit 1
    }
    Write-Host "Found: $sysPy" -ForegroundColor Green
    Write-Step "python -m venv .venv"
    & $sysPy -m venv (Join-Path $Root ".venv")
    if (-not (Test-Path $venvPy)) {
        Write-Err "Failed to create .venv"
        exit 1
    }
}

$py = (Resolve-Path $venvPy).Path
Write-Step "Python (venv): $py"

# Always run pip when not -SkipInstall (idempotent). Old "skip" logic missed broken venvs.
if (-not $SkipInstall) {
    if ($ForceInstall) { Write-Step "ForceInstall: reinstalling all packages" }
    # Yalnızca editable kurulum: bağımlılıklar pyproject.toml'dan gelir (requirements.txt ile
    # sürüm çakışması / eski dosyanın langchain-google-genai'yi 2.x'e düşürmesi olmaz).
    Write-Step "pip install -e .  (pyproject.toml)"
    & $py -m pip install --upgrade pip setuptools wheel
    if ($ForceInstall) {
        & $py -m pip install --force-reinstall -e $Root
    } else {
        & $py -m pip install -e $Root
    }
    Write-Step "playwright install chromium"
    & $py -m playwright install chromium
    Write-Step "Verify core imports"
    Test-ImportsOrExit -PythonExe $py
}

if ($InstallOnly) {
    Write-Host "`nDone. Start bot: .\Run.ps1 -SkipInstall" -ForegroundColor Green
    exit 0
}

Ensure-DotEnv

Write-Step "Starting Telegram bot (Ctrl+C to stop)"
if (-not $env:PLAYWRIGHT_HEADLESS) {
    $env:PLAYWRIGHT_HEADLESS = "false"
}
& $py -m app.main
