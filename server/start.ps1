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
    $toolsReady = $false

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

    try {
        $toolsJson = (& openclaw config get tools 2>$null) -join "`n"
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($toolsJson)) {
            $tools = $toolsJson | ConvertFrom-Json
            $allow = @($tools.allow)
            $alsoAllow = @($tools.alsoAllow)
            $deny = @($tools.deny)
            $patchrelayToolsAllowed = (
                $tools.profile -eq "full" -or
                $tools.profile -eq "full-permission" -or
                $tools.profile -eq "full-permisson" -or
                $allow -contains "group:plugins" -or
                $allow -contains "patchrelay" -or
                $alsoAllow -contains "group:plugins" -or
                $alsoAllow -contains "patchrelay" -or
                (
                    $allow -contains "patchrelay_submit_task" -and
                    $allow -contains "patchrelay_get_task" -and
                    $allow -contains "patchrelay_cancel_task"
                ) -or
                (
                    $alsoAllow -contains "patchrelay_submit_task" -and
                    $alsoAllow -contains "patchrelay_get_task" -and
                    $alsoAllow -contains "patchrelay_cancel_task"
                )
            )
            $patchrelayToolsDenied = (
                $deny -contains "*" -or
                $deny -contains "group:plugins" -or
                $deny -contains "patchrelay" -or
                $deny -contains "patchrelay_submit_task" -or
                $deny -contains "patchrelay_get_task" -or
                $deny -contains "patchrelay_cancel_task"
            )
            $toolsReady = ($patchrelayToolsAllowed -and -not $patchrelayToolsDenied)
        }
    } catch {
        $toolsReady = $false
    }

    return ($pluginReady -and $skillReady -and $toolsReady)
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

# Read token from config. Never hard-code a real token here — that would leak a
# secret into version control. If the config is missing or has no token, stop
# and tell the user to run setup rather than falling back to a baked-in value.
Write-Host "Reading configuration..." -ForegroundColor Yellow
$token = $null
if (Test-Path ".\patchrelay.yaml") {
    $configContent = Get-Content ".\patchrelay.yaml" -Raw
    if ($configContent -match 'token:\s*(.+)') {
        $token = $Matches[1].Trim()
    }
}
if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "No server.token found in patchrelay.yaml." -ForegroundColor Red
    Write-Host "Run: uv run patchrelay setup --config .\patchrelay.yaml --yes" -ForegroundColor Yellow
    exit 1
}

Write-Host "Token: (loaded from patchrelay.yaml)" -ForegroundColor Green
Write-Host ""

# Read the OpenClaw gateway endpoint from its own config so the gateway we
# (re)start below is the exact one `openclaw dashboard`, `openclaw status`, and
# the CLI connect to. If start.ps1 launched a gateway on a different port/token
# than the config declares, the Dashboard would talk to a separate (often stale)
# gateway that never reloaded the freshly-applied PatchRelay tool/skill config,
# so Agent1 would not see patchrelay_* tools even though config is correct.
$openclawConfigPath = Join-Path $env:USERPROFILE ".openclaw\openclaw.json"
$gatewayPort = 19001
$gatewayToken = "openclaw-local-token"
if (Test-Path $openclawConfigPath) {
    try {
        $openclawConfig = Get-Content $openclawConfigPath -Raw | ConvertFrom-Json
        if ($openclawConfig.gateway.port) { $gatewayPort = [int]$openclawConfig.gateway.port }
        if ($openclawConfig.gateway.auth.token) { $gatewayToken = [string]$openclawConfig.gateway.auth.token }
    } catch {
        Write-Host "Could not parse $openclawConfigPath; using gateway defaults ${gatewayPort}." -ForegroundColor Yellow
    }
}
Write-Host "Gateway endpoint: http://127.0.0.1:$gatewayPort (from OpenClaw config)" -ForegroundColor Green
Write-Host ""

# 1. Ensure OpenClaw can see PatchRelay tools and skill
Write-Host "[1/5] Checking OpenClaw PatchRelay integration..." -ForegroundColor Yellow
if (Test-OpenClawPatchRelayReady) {
    Write-Host "OpenClaw PatchRelay plugin, skill, and tools are already ready." -ForegroundColor Green
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
# A schtasks "Gateway service" may already own the config port. Prefer restarting
# that service (reloads config + plugins, no port conflict); fall back to a
# foreground gateway only when no service is installed. A plain `gateway run
# --force` here would fight the service for the port and fail to bind.
Write-Host "[2/5] Launching OpenClaw Gateway..." -ForegroundColor Yellow
$gatewayCmd = "Set-Location '$ServerDir'; `$env:OPENCLAW_SKIP_STARTUP_MODEL_PREWARM = '1'; Write-Host '================================================' -ForegroundColor Cyan; Write-Host '  OpenClaw Gateway' -ForegroundColor White; Write-Host '  Port: $gatewayPort' -ForegroundColor Yellow; Write-Host '================================================' -ForegroundColor Cyan; Write-Host ''; openclaw gateway restart; if (`$LASTEXITCODE -ne 0) { Write-Host 'No gateway service; starting foreground gateway...' -ForegroundColor Yellow; openclaw gateway run --port $gatewayPort --auth token --token $gatewayToken --bind loopback --force }"
Start-Process $PowerShellExe -ArgumentList "-NoExit", "-Command", $gatewayCmd
Start-Sleep -Seconds 4

# 3. Launch PatchRelay Server
Write-Host "[3/5] Launching PatchRelay Server..." -ForegroundColor Yellow
$serverCmd = "Set-Location '$ServerDir'; Write-Host '================================================' -ForegroundColor Cyan; Write-Host '  PatchRelay Server' -ForegroundColor White; Write-Host '  Port: 8787' -ForegroundColor Yellow; Write-Host '================================================' -ForegroundColor Cyan; Write-Host ''; Write-Host 'Waiting for Gateway...' -ForegroundColor Gray; Start-Sleep 6; uv run patchrelay serve --config .\patchrelay.yaml"
Start-Process $PowerShellExe -ArgumentList "-NoExit", "-Command", $serverCmd
Start-Sleep -Seconds 4

# 4. Launch PatchRelay TUI
Write-Host "[4/5] Launching PatchRelay TUI..." -ForegroundColor Yellow
$tuiCmd = "Set-Location '$ServerDir'; Write-Host '================================================' -ForegroundColor Cyan; Write-Host '  PatchRelay TUI Monitor' -ForegroundColor White; Write-Host '================================================' -ForegroundColor Cyan; Write-Host ''; Write-Host 'Waiting for services...' -ForegroundColor Gray; Start-Sleep 12; uv run patchrelay ui --config .\patchrelay.yaml --url http://127.0.0.1:8787 --token $token --gateway-url http://127.0.0.1:$gatewayPort --gateway-token $gatewayToken --gateway-bind loopback"
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
Write-Host "  Window 1: OpenClaw Gateway (Port $gatewayPort)" -ForegroundColor Cyan
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
