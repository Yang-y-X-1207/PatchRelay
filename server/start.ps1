# PatchRelay Complete Environment - One-Click Startup
# This script launches all services in separate visible windows

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  PatchRelay Environment Startup" -ForegroundColor White
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

function Add-WindowsPathEntry {
    param([string]$Entry)

    if ([string]::IsNullOrWhiteSpace($Entry) -or -not (Test-Path $Entry)) {
        return
    }

    $parts = @($env:Path -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($parts -notcontains $Entry) {
        $env:Path = "$Entry;$env:Path"
    }
}

function Test-OpenClawPatchRelayReady {
    $pluginReady = $false
    $skillReady = $false

    try {
        $pluginJson = (& openclaw plugins inspect patchrelay --runtime --json 2>$null) -join "`n"
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($pluginJson)) {
            $plugin = $pluginJson | ConvertFrom-Json
            $toolNames = @($plugin.plugin.toolNames)
            $pluginReady = (
                $plugin.plugin.enabled -eq $true -and
                $plugin.plugin.activated -eq $true -and
                $plugin.plugin.status -eq "loaded" -and
                $toolNames -contains "patchrelay_submit_task" -and
                $toolNames -contains "patchrelay_get_task" -and
                $toolNames -contains "patchrelay_cancel_task"
            )
        }
    } catch {
        $pluginReady = $false
    }

    try {
        $skillInfo = (& openclaw skills info patchrelay 2>&1) -join "`n"
        $skillReady = (
            $LASTEXITCODE -eq 0 -and
            $skillInfo -match "Visible to model:\s*yes" -and
            $skillInfo -match "Ready"
        )
    } catch {
        $skillReady = $false
    }

    return ($pluginReady -and $skillReady)
}

$WindowsRoot = $env:SystemRoot
if ([string]::IsNullOrWhiteSpace($WindowsRoot)) {
    $WindowsRoot = $env:WINDIR
}
if ([string]::IsNullOrWhiteSpace($WindowsRoot)) {
    $WindowsRoot = "C:\Windows"
}

Add-WindowsPathEntry (Join-Path $WindowsRoot "System32")
Add-WindowsPathEntry (Join-Path $WindowsRoot "System32\Wbem")
Add-WindowsPathEntry (Join-Path $WindowsRoot "System32\WindowsPowerShell\v1.0")

$PowerShellExe = Join-Path $WindowsRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $PowerShellExe)) {
    $PowerShellExe = "powershell"
}
$CmdExe = Join-Path $WindowsRoot "System32\cmd.exe"
if (-not (Test-Path $CmdExe)) {
    $CmdExe = "cmd.exe"
}

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

# 1. Ensure OpenClaw can see PatchRelay tools and skill
Write-Host "[1/5] Checking OpenClaw PatchRelay integration..." -ForegroundColor Yellow
if (Test-OpenClawPatchRelayReady) {
    Write-Host "OpenClaw PatchRelay plugin and skill are already ready." -ForegroundColor Green
} else {
    Write-Host "PatchRelay OpenClaw integration is missing; applying setup..." -ForegroundColor Yellow
    uv run patchrelay openclaw apply --config .\patchrelay.yaml --apply
    if ($LASTEXITCODE -ne 0) {
        Write-Host "OpenClaw PatchRelay setup failed. Startup stopped." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}
Write-Host ""

# 2. Launch OpenClaw Gateway
Write-Host "[2/5] Launching OpenClaw Gateway..." -ForegroundColor Yellow
$gatewayCmd = "Set-Location '$ServerDir'; `$env:OPENCLAW_SKIP_STARTUP_MODEL_PREWARM = '1'; Write-Host '================================================' -ForegroundColor Cyan; Write-Host '  OpenClaw Gateway' -ForegroundColor White; Write-Host '  Port: 19001' -ForegroundColor Yellow; Write-Host '================================================' -ForegroundColor Cyan; Write-Host ''; openclaw gateway run --port 19001 --auth token --token openclaw-local-token --bind loopback --force"
Start-Process $PowerShellExe -ArgumentList "-NoExit", "-Command", $gatewayCmd
Start-Sleep -Seconds 4

# 3. Launch PatchRelay Server
Write-Host "[3/5] Launching PatchRelay Server..." -ForegroundColor Yellow
$serverCmd = "Set-Location '$ServerDir'; Write-Host '================================================' -ForegroundColor Cyan; Write-Host '  PatchRelay Server' -ForegroundColor White; Write-Host '  Port: 8787' -ForegroundColor Yellow; Write-Host '================================================' -ForegroundColor Cyan; Write-Host ''; Write-Host 'Waiting for Gateway...' -ForegroundColor Gray; Start-Sleep 6; uv run patchrelay serve --config .\patchrelay.yaml"
Start-Process $PowerShellExe -ArgumentList "-NoExit", "-Command", $serverCmd
Start-Sleep -Seconds 4

# 4. Launch PatchRelay TUI
Write-Host "[4/5] Launching PatchRelay TUI..." -ForegroundColor Yellow
$tuiCmd = "Set-Location '$ServerDir'; Write-Host '================================================' -ForegroundColor Cyan; Write-Host '  PatchRelay TUI Monitor' -ForegroundColor White; Write-Host '================================================' -ForegroundColor Cyan; Write-Host ''; Write-Host 'Waiting for services...' -ForegroundColor Gray; Start-Sleep 12; uv run patchrelay ui --config .\patchrelay.yaml --url http://127.0.0.1:8787 --token $token --gateway-url http://127.0.0.1:19001 --gateway-token openclaw-local-token --gateway-bind loopback"
Start-Process $PowerShellExe -ArgumentList "-NoExit", "-Command", $tuiCmd
Start-Sleep -Seconds 3

# 5. Open Dashboard
Write-Host "[5/5] Opening OpenClaw Dashboard..." -ForegroundColor Yellow
Start-Sleep -Seconds 6
Start-Process $CmdExe -ArgumentList "/c", "openclaw dashboard --yes" -WindowStyle Hidden

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
