# Restart both paper loops, detached, on the CURRENT working tree.
#
#   powershell -ExecutionPolicy Bypass -File scripts\restart_loops.ps1 -Expiry 2026-09-04
#
# WHY A SCRIPT AND NOT TWO PASTED COMMANDS
# ----------------------------------------
# The two loops differ in role, brain set, shadow set and profile, and getting
# any one of those wrong sends orders to one account and stamps the rows with
# another account's name (config.credentials refuses that disagreement, so the
# failure is loud -- but only if the pair is written down somewhere). This file
# IS that written-down pair.
#
# Python caches imports at process start, so a code fix does not reach a running
# loop. That is why a pricing change needs a restart and not just a commit.
#
# Detached via Start-Process so the loops survive this shell closing. They still
# die with the laptop -- Railway deployment remains Murat's call.

param(
    [Parameter(Mandatory = $true)][string]$Expiry,
    [string]$Tag = "s14",
    # LEGACY MODE. Exits, fills and marking continue; the entry pass never runs,
    # so the book can only get smaller. This is how dev and exp1 are wound down
    # as PRE_UNITS_FIX books: their positions were opened under the pricing bug
    # fixed on 27 Aug, so their exits are still wanted and their entries are not.
    [switch]$ManageOnly
)

$repo = Split-Path -Parent $PSScriptRoot
$py   = "C:\Users\mrthn\AppData\Local\Programs\Python\Python312\python.exe"

if (-not (Test-Path $py)) { throw "python not found at $py" }

# Refuse to start a second copy beside a live one. Two loops on one account is
# two writers to the same ledger, which is what broke the hash chain on 25 Aug.
$running = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'agent_loop' }
if ($running) {
    Write-Host "REFUSING: agent_loop already running (PIDs: $($running.ProcessId -join ', '))."
    Write-Host "Stop them first:  Stop-Process -Id $($running.ProcessId -join ',') -Force"
    exit 1
}

$loops = @(
    @{ Role = "dev";  Args = @("--profile", "conservative") },
    @{ Role = "exp1"; Args = @("--brains", "vol_gap,event_move,options_attention,narrative_dispersion",
                               "--shadow", "vol_gap,event_move") }
)

foreach ($l in $loops) {
    $role = $l.Role
    $out  = Join-Path $repo "state\loop_${role}_${Tag}.log"
    $err  = Join-Path $repo "state\loop_${role}_${Tag}.err"
    $argv = @("-m", "scripts.agent_loop", "--expiry", $Expiry, "--live") + $l.Args
    if ($ManageOnly) { $argv += "--manage-only" }

    # Per-process role. Set in the CHILD's environment only -- setting it in this
    # shell would leak into the second loop and silently point both at one account.
    $env:AAT_ACCOUNT_ROLE = $role
    $p = Start-Process -FilePath $py -ArgumentList $argv `
        -WorkingDirectory $repo -RedirectStandardOutput $out -RedirectStandardError $err `
        -WindowStyle Hidden -PassThru
    $mode = if ($ManageOnly) { "MANAGE-ONLY (no new risk)" } else { "trading" }
    Write-Host ("started {0,-5} pid {1,-6} expiry {2}  {3}  -> {4}" -f $role, $p.Id, $Expiry, $mode, $out)
    Start-Sleep -Milliseconds 1500
}
Remove-Item Env:\AAT_ACCOUNT_ROLE -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Verify with:  python -m scripts.liveness"
Write-Host "Liveness becomes authoritative BY ROLE only after this restart --"
Write-Host "the previous loops predated the heartbeat and could only be seen by process scan."
