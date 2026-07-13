# Stop all PatchRelay services

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Stopping All Services" -ForegroundColor White
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$stopped = 0

# 1. Stop PatchRelay Server (uvicorn/python)
Write-Host "Stopping PatchRelay Server..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
        if ($cmdline -like "*patchrelay*" -or $cmdline -like "*uvicorn*") {
            Stop-Process -Id $_.Id -Force
            Write-Host "  [OK] Stopped PatchRelay Server (PID: $($_.Id))" -ForegroundColor Green
            $stopped++
        }
    } catch {
        # Process might have already exited
    }
}

# 2. Stop OpenClaw Gateway (node)
Write-Host "Stopping OpenClaw Gateway..." -ForegroundColor Yellow
Get-Process node -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
        if ($cmdline -like "*openclaw*gateway*" -or $cmdline -like "*openclaw-gateway*") {
            Stop-Process -Id $_.Id -Force
            Write-Host "  [OK] Stopped OpenClaw Gateway (PID: $($_.Id))" -ForegroundColor Green
            $stopped++
        }
    } catch {
        # Process might have already exited
    }
}

# 3. Stop OpenClaw Dashboard (node)
Write-Host "Stopping OpenClaw Dashboard..." -ForegroundColor Yellow
Get-Process node -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
        if ($cmdline -like "*openclaw*dashboard*" -and $cmdline -notlike "*gateway*") {
            Stop-Process -Id $_.Id -Force
            Write-Host "  [OK] Stopped OpenClaw Dashboard (PID: $($_.Id))" -ForegroundColor Green
            $stopped++
        }
    } catch {
        # Process might have already exited
    }
}

# 4. Stop any remaining uv processes
Write-Host "Cleaning up UV processes..." -ForegroundColor Yellow
Get-Process uv -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        Stop-Process -Id $_.Id -Force
        Write-Host "  [OK] Stopped UV process (PID: $($_.Id))" -ForegroundColor Green
        $stopped++
    } catch {
        # Process might have already exited
    }
}

# 5. Check ports and kill processes using them
Write-Host "Checking ports..." -ForegroundColor Yellow

# Include the gateway port from the OpenClaw config (the endpoint start.ps1 now
# launches on) plus the legacy 19001 port so older sessions are also cleaned up.
$ports = @(8787, 19001)
$openclawConfigPath = Join-Path $env:USERPROFILE ".openclaw\openclaw.json"
if (Test-Path $openclawConfigPath) {
    try {
        $openclawConfig = Get-Content $openclawConfigPath -Raw | ConvertFrom-Json
        if ($openclawConfig.gateway.port) { $ports += [int]$openclawConfig.gateway.port }
    } catch {
        # Config unreadable; fall back to the default port list.
    }
}
$ports = $ports | Sort-Object -Unique
foreach ($port in $ports) {
    $connections = C:\\Windows\\System32\\netstat.exe -ano | Select-String ":$port " | Select-String "LISTENING"
    foreach ($conn in $connections) {
        if ($conn -match '\s+(\d+)\s*$') {
            $pid = $Matches[1]
            try {
                $proc = Get-Process -Id $pid -ErrorAction Stop
                Stop-Process -Id $pid -Force
                Write-Host "  [OK] Stopped process on port $port (PID: $pid)" -ForegroundColor Green
                $stopped++
            } catch {
                # Process might have already exited
            }
        }
    }
}

Write-Host ""
if ($stopped -gt 0) {
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "  Stopped $stopped process(es)" -ForegroundColor Green
    Write-Host "================================================" -ForegroundColor Green
} else {
    Write-Host "================================================" -ForegroundColor Yellow
    Write-Host "  No running services found" -ForegroundColor Yellow
    Write-Host "================================================" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "To restart: .\start.ps1" -ForegroundColor Gray
Write-Host ""
