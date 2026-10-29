<#
.SYNOPSIS
  Run the evidence assistant for devices on your Tailscale tailnet, on one port (default 10012).

.DESCRIPTION
  Starts (or reuses) the embedded dev database, runs the FastAPI backend on 127.0.0.1 only, and
  serves the Next.js frontend on 0.0.0.0:<Port>. The browser talks only to Next; Next proxies
  /api/* to the backend, so the backend is never exposed. Then open http://<tailscale-ip>:<Port>.

  Production build by default (faster, stable over the tailnet). Use -Dev for hot reload.

.PARAMETER OpenFirewall
  Adds an inbound Windows Firewall rule for <Port>, limited to Tailscale addresses (100.64.0.0/10).
  Needs an elevated (Administrator) PowerShell. Only needed once.

.EXAMPLE
  ./scripts/tailnet.ps1
  ./scripts/tailnet.ps1 -Dev
  ./scripts/tailnet.ps1 -OpenFirewall      # once, from an Administrator PowerShell
  ./scripts/tailnet.ps1 -Stop
#>
param(
  [int]$Port = 10012,
  [int]$BackendPort = 8000,
  [switch]$Dev,
  [switch]$SkipBuild,
  [switch]$OpenFirewall,
  [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$logs = Join-Path $root '.run'
New-Item -ItemType Directory -Force $logs | Out-Null

function Stop-Port([int]$p) {
  Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}

if ($Stop) {
  Stop-Port $Port
  Stop-Port $BackendPort
  & $python (Join-Path $backend 'scripts\dev_db.py') --stop
  Write-Host 'Stopped.'
  return
}

if ($OpenFirewall) {
  $name = "BPI Evidence Assistant (Tailscale) $Port"
  if (-not (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP `
      -LocalPort $Port -RemoteAddress '100.64.0.0/10' -Profile Any | Out-Null
    Write-Host "Firewall rule added: $name"
  } else {
    Write-Host "Firewall rule already present: $name"
  }
}

if (-not (Test-Path $python)) {
  throw "No backend virtualenv. Run: cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
}
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
  Push-Location $frontend; npm ci; Pop-Location
}

# 1. Database (idempotent: reuses a running server, migrates, seeds if empty).
& $python (Join-Path $backend 'scripts\dev_db.py')

# 2. Backend, loopback only.
Stop-Port $BackendPort
$api = Start-Process -FilePath $python -WorkingDirectory $backend -WindowStyle Hidden -PassThru `
  -ArgumentList @('-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', "$BackendPort") `
  -RedirectStandardOutput (Join-Path $logs 'backend.log') -RedirectStandardError (Join-Path $logs 'backend.err.log')

# 3. Frontend on all interfaces; /api/* is proxied to the backend.
Stop-Port $Port
$env:BACKEND_URL = "http://127.0.0.1:$BackendPort"
$ts = $null
try { $ts = (& tailscale ip -4 2>$null | Select-Object -First 1) } catch { }
if ($ts) { $env:DEV_ORIGINS = $ts }

Push-Location $frontend
try {
  if ($Dev) {
    $mode = 'dev'
    $nextArgs = @('next', 'dev', '-H', '0.0.0.0', '-p', "$Port")
  } else {
    $mode = 'production'
    if (-not $SkipBuild) { npx next build; if ($LASTEXITCODE) { throw 'next build failed' } }
    $nextArgs = @('next', 'start', '-H', '0.0.0.0', '-p', "$Port")
  }
  $web = Start-Process -FilePath 'npx.cmd' -ArgumentList $nextArgs -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs 'frontend.log') -RedirectStandardError (Join-Path $logs 'frontend.err.log')
} finally { Pop-Location }

# Wait until both answer.
$deadline = (Get-Date).AddSeconds(90)
do {
  Start-Sleep -Milliseconds 800
  try { $ok = (Invoke-WebRequest "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { $ok = $false }
} until ($ok -or (Get-Date) -gt $deadline)

if (-not $ok) { Write-Warning "Not answering yet; see $logs\*.log" }
Write-Host ""
Write-Host "Evidence assistant ($mode) is running."
Write-Host "  This PC:    http://localhost:$Port"
if ($ts) { Write-Host "  Tailnet:    http://${ts}:$Port" }
Write-Host "  Logs:       $logs"
Write-Host "  Stop with:  ./scripts/tailnet.ps1 -Stop"
