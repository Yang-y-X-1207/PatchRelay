# PatchRelay Relay Launcher
# Choose two agents to bridge: Agent1 (the front agent you talk to) and
# Agent2 (the delegate that runs the coding work). PatchRelay relays between
# them. Run with no arguments for an interactive menu, or pass -Agent1/-Agent2
# to skip it. Use -DryRun to print what would happen without launching anything.
#
#   Forward  : Agent1 = openclaw           -> full gateway stack, delegates to Agent2
#   Ping-pong: Agent1 = claude | codex     -> desktop session, relays to Agent2
[CmdletBinding()]
param(
    [ValidateSet("openclaw", "claude", "codex")]
    [string]$Agent1,
    [ValidateSet("claude", "codex")]
    [string]$Agent2,
    [switch]$DryRun
)

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  PatchRelay Relay Launcher" -ForegroundColor White
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$ServerDir = $PSScriptRoot
Set-Location $ServerDir

function Read-ConfigValue {
    param([string]$Key)  # top-level.sub, e.g. "server.token" or "repo.path"
    if (-not (Test-Path ".\patchrelay.yaml")) { return $null }
    $parts = $Key.Split(".")
    $section = $parts[0]
    $leaf = $parts[1]
    $inSection = $false
    foreach ($line in Get-Content ".\patchrelay.yaml") {
        if ($line -match "^(\S+):") {
            $inSection = ($Matches[1] -eq $section)
            continue
        }
        if ($inSection -and $line -match "^\s+$([regex]::Escape($leaf)):\s*(.+?)\s*$") {
            return $Matches[1].Trim()
        }
    }
    return $null
}

function Select-FromMenu {
    param([string]$Title, [string[]]$Options)
    Write-Host $Title -ForegroundColor White
    for ($i = 0; $i -lt $Options.Count; $i++) {
        Write-Host ("  [{0}] {1}" -f ($i + 1), $Options[$i]) -ForegroundColor Cyan
    }
    while ($true) {
        $choice = Read-Host "Enter number"
        $n = 0
        if ([int]::TryParse($choice, [ref]$n) -and $n -ge 1 -and $n -le $Options.Count) {
            return $Options[$n - 1]
        }
        Write-Host "Invalid choice, try again." -ForegroundColor Red
    }
}

# Interactive selection when not passed on the command line.
if (-not $Agent1) {
    Write-Host "Agent1 is the front agent you talk to directly." -ForegroundColor Gray
    Write-Host ""
    $Agent1 = Select-FromMenu "Choose Agent1 (front agent):" @("openclaw", "claude", "codex")
    Write-Host ""
}
if (-not $Agent2) {
    Write-Host "Agent2 is the delegate that runs the coding work." -ForegroundColor Gray
    Write-Host ""
    # Agent2 must be a worker agent and cannot equal Agent1.
    $agent2Options = @("claude", "codex") | Where-Object { $_ -ne $Agent1 }
    $Agent2 = Select-FromMenu "Choose Agent2 (delegate):" $agent2Options
    Write-Host ""
}

# Validate the pair.
if ($Agent1 -eq $Agent2) {
    Write-Host "Agent1 and Agent2 must be different agents." -ForegroundColor Red
    exit 1
}
if ($Agent2 -notin @("claude", "codex")) {
    Write-Host "Agent2 must be 'claude' or 'codex' (the delegate runs the coding work)." -ForegroundColor Red
    exit 1
}

$mode = if ($Agent1 -eq "openclaw") { "forward" } else { "pingpong" }

Write-Host "------------------------------------------------" -ForegroundColor DarkGray
Write-Host ("  Agent1 (front)    : {0}" -f $Agent1) -ForegroundColor Green
Write-Host ("  Agent2 (delegate) : {0}" -f $Agent2) -ForegroundColor Green
Write-Host ("  Topology          : {0}" -f $mode) -ForegroundColor Green
Write-Host "------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# Set worker.default in patchrelay.yaml to Agent2 (line-based so we only touch
# the 'default:' inside the 'worker:' block, never the one under 'tests:').
function Set-WorkerDefault {
    param([string]$Worker)
    if (-not (Test-Path ".\patchrelay.yaml")) {
        Write-Host "patchrelay.yaml not found; run 'uv run patchrelay setup' first." -ForegroundColor Red
        exit 1
    }
    $lines = Get-Content ".\patchrelay.yaml"
    $inWorker = $false
    $changed = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^(\S+):") {
            $inWorker = ($Matches[1] -eq "worker")
            continue
        }
        if ($inWorker -and $lines[$i] -match "^(\s+)default:\s*") {
            $lines[$i] = "$($Matches[1])default: $Worker"
            $changed = $true
            break
        }
    }
    if ($changed) {
        Set-Content ".\patchrelay.yaml" $lines
        Write-Host "Set worker.default = $Worker in patchrelay.yaml" -ForegroundColor Green
    } else {
        Write-Host "Could not find worker.default in patchrelay.yaml; leaving as-is." -ForegroundColor Yellow
    }
}

if ($mode -eq "forward") {
    # Agent1 = OpenClaw. The delegate is whatever worker OpenClaw submits with;
    # 'auto' resolves to worker.default, so point that at Agent2 and reuse the
    # existing full-stack startup (gateway + server + TUI + dashboard).
    if ($DryRun) {
        Write-Host "[DryRun] Would set worker.default = $Agent2" -ForegroundColor Magenta
        Write-Host "[DryRun] Would run .\start.ps1 (gateway + server + TUI + dashboard)" -ForegroundColor Magenta
        exit 0
    }
    Set-WorkerDefault $Agent2
    Write-Host "Starting forward stack via start.ps1..." -ForegroundColor Yellow
    Write-Host ""
    & (Join-Path $ServerDir "start.ps1")
    exit $LASTEXITCODE
}

# --- Ping-pong mode: Agent1 = claude|codex on the desktop, relays to Agent2 ---

$token = Read-ConfigValue "server.token"
if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "No server.token in patchrelay.yaml; run 'uv run patchrelay setup' first." -ForegroundColor Red
    exit 1
}
$repoPath = Read-ConfigValue "repo.path"
if ([string]::IsNullOrWhiteSpace($repoPath)) { $repoPath = $ServerDir }
if ($repoPath -eq ".") { $repoPath = $ServerDir }
$patchrelayUrl = "http://127.0.0.1:8787"
$agent1File = Join-Path $ServerDir "agent1\$Agent1-agent1.md"

if ($DryRun) {
    Write-Host "[DryRun] Would set worker.default = $Agent2" -ForegroundColor Magenta
    Write-Host "[DryRun] Would start PatchRelay server (port 8787) + TUI" -ForegroundColor Magenta
    Write-Host ("[DryRun] Would open desktop {0} with:" -f $Agent1) -ForegroundColor Magenta
    Write-Host ("           PATCHRELAY_URL={0}" -f $patchrelayUrl) -ForegroundColor Magenta
    Write-Host ("           PATCHRELAY_PARTNER={0}" -f $Agent2) -ForegroundColor Magenta
    Write-Host ("           repo cwd={0}" -f $repoPath) -ForegroundColor Magenta
    Write-Host ("           instructions={0}" -f $agent1File) -ForegroundColor Magenta
    exit 0
}

Set-WorkerDefault $Agent2

# 1. PatchRelay server
Write-Host "[1/3] Launching PatchRelay Server (port 8787)..." -ForegroundColor Yellow
$serverCmd = "Set-Location '$ServerDir'; Write-Host 'PatchRelay Server (port 8787)' -ForegroundColor Cyan; uv run patchrelay serve --config .\patchrelay.yaml"
Start-Process "powershell" -ArgumentList "-NoExit", "-Command", $serverCmd
Start-Sleep -Seconds 6

# 2. PatchRelay TUI
Write-Host "[2/3] Launching PatchRelay TUI..." -ForegroundColor Yellow
$tuiCmd = "Set-Location '$ServerDir'; Write-Host 'PatchRelay TUI' -ForegroundColor Cyan; Start-Sleep 4; uv run patchrelay ui --config .\patchrelay.yaml --url $patchrelayUrl --token $token"
Start-Process "powershell" -ArgumentList "-NoExit", "-Command", $tuiCmd
Start-Sleep -Seconds 2

# 3. Desktop Agent1 session (relays to Agent2 via the patchrelay CLI)
Write-Host ("[3/3] Opening desktop {0} as Agent1..." -f $Agent1) -ForegroundColor Yellow
$envPrelude = "`$env:PATCHRELAY_URL='$patchrelayUrl'; `$env:PATCHRELAY_TOKEN='$token'; `$env:PATCHRELAY_PARTNER='$Agent2'; Set-Location '$repoPath';"
if ($Agent1 -eq "claude") {
    # Inject the Agent1 contract via a file (avoids Windows argv newline truncation).
    $agent1Cmd = "$envPrelude Write-Host 'Agent1 = claude, delegate = $Agent2' -ForegroundColor Cyan; claude --append-system-prompt-file '$agent1File'"
} else {
    # Point Codex at the absolute-path instruction file in its opening prompt so
    # it reads the Agent1 contract itself — no repo pollution (no AGENTS.md copy),
    # and the short single-line prompt sidesteps Windows argv newline truncation.
    $agent1Cmd = "$envPrelude Write-Host 'Agent1 = codex, delegate = $Agent2' -ForegroundColor Cyan; codex `"Read the file $agent1File - it defines your role as Agent1 relaying coding tasks to $Agent2 via the patchrelay CLI. Follow it. Then greet the user and wait for a task.`""
}
Start-Process "powershell" -ArgumentList "-NoExit", "-Command", $agent1Cmd

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  Ping-pong relay started" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ("  Agent1 (front)    : {0}  <- talk to this window" -f $Agent1) -ForegroundColor Cyan
Write-Host ("  Agent2 (delegate) : {0}" -f $Agent2) -ForegroundColor Cyan
Write-Host "  PatchRelay Server : port 8787" -ForegroundColor Cyan
Write-Host "  TUI               : monitor window" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop all services: .\stop.ps1" -ForegroundColor Yellow
Write-Host ""
