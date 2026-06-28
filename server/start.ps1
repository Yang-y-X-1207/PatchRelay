# PatchRelay Complete Environment - One-Click Startup
# This script launches all services in separate visible windows

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  PatchRelay Environment Startup" -ForegroundColor White
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$ServerDir = $PSScriptRoot

# Ensure we're in the right directory
Set-Location $ServerDir

# Read token from config
Write-Host "Reading configuration..." -ForegroundColor Yellow
$token = "UEbjEGJaLR_UwEeHXf4PGAoTyzLIDJttXD2Ma6kt6JU"
if (Test-Path ".\patchrelay.yaml") {
    $configContent = Get-Content ".\patchrelay.yaml" -Raw
    if ($configContent -match 'token:\s*(.+)') {
        $token = $Matches[1].Trim()
    }
}

Write-Host "Token: $token" -ForegroundColor Green
Write-Host ""

# 1. Launch OpenClaw Gateway
Write-Host "[1/4] Launching OpenClaw Gateway..." -ForegroundColor Yellow
$gatewayCmd = "Write-Host '================================================' -ForegroundColor Cyan; Write-Host '  OpenClaw Gateway' -ForegroundColor White; Write-Host '  Port: 19001' -ForegroundColor Yellow; Write-Host '================================================' -ForegroundColor Cyan; Write-Host ''; openclaw gateway"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $gatewayCmd
Start-Sleep -Seconds 4

# 2. Launch PatchRelay Server
Write-Host "[2/4] Launching PatchRelay Server..." -ForegroundColor Yellow
$serverCmd = "Set-Location '$ServerDir'; Write-Host '================================================' -ForegroundColor Cyan; Write-Host '  PatchRelay Server' -ForegroundColor White; Write-Host '  Port: 8787' -ForegroundColor Yellow; Write-Host '================================================' -ForegroundColor Cyan; Write-Host ''; Write-Host 'Waiting for Gateway...' -ForegroundColor Gray; Start-Sleep 6; uv run patchrelay serve --config .\patchrelay.yaml"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $serverCmd
Start-Sleep -Seconds 4

# 3. Launch PatchRelay TUI
Write-Host "[3/4] Launching PatchRelay TUI..." -ForegroundColor Yellow
$tuiCmd = "Set-Location '$ServerDir'; Write-Host '================================================' -ForegroundColor Cyan; Write-Host '  PatchRelay TUI Monitor' -ForegroundColor White; Write-Host '================================================' -ForegroundColor Cyan; Write-Host ''; Write-Host 'Waiting for services...' -ForegroundColor Gray; Start-Sleep 12; uv run patchrelay ui --config .\patchrelay.yaml --url http://127.0.0.1:8787 --token $token --gateway-url http://127.0.0.1:19001 --gateway-token openclaw-local-token --gateway-bind loopback"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $tuiCmd
Start-Sleep -Seconds 3

# 4. Open Dashboard
Write-Host "[4/4] Opening OpenClaw Dashboard..." -ForegroundColor Yellow
Start-Sleep -Seconds 6
Start-Process cmd.exe -ArgumentList "/c", "openclaw dashboard --yes" -WindowStyle Hidden

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  Startup Complete!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Running Services (3 windows + browser):" -ForegroundColor White
Write-Host "  Window 1: OpenClaw Gateway (Port 19001)" -ForegroundColor Cyan
Write-Host "  Window 2: PatchRelay Server (Port 8787)" -ForegroundColor Cyan
Write-Host "  Window 3: PatchRelay TUI Monitor" -ForegroundColor Cyan
Write-Host "  Browser:  OpenClaw Dashboard" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor White
Write-Host "  1. Wait for all windows to show 'ready'" -ForegroundColor Gray
Write-Host "  2. Chat in OpenClaw Dashboard" -ForegroundColor Gray
Write-Host "  3. Ask AI to help with coding tasks" -ForegroundColor Gray
Write-Host ""
Write-Host "Gateway Token: $token" -ForegroundColor Yellow
Write-Host ""
Write-Host "To stop all services: .\stop.ps1" -ForegroundColor Yellow
Write-Host "You can close this window now." -ForegroundColor Gray
Write-Host ""
