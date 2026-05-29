<#
.SYNOPSIS
  Install (or remove) a Windows Scheduled Task that runs one PrivacyMirror pass
  daily, so removals and recurring re-removals keep happening when the app is closed.

.EXAMPLE
  .\schedule-task.ps1                 # install, runs daily at 09:00
  .\schedule-task.ps1 -Time 18:30     # install, runs daily at 6:30 PM
  .\schedule-task.ps1 -Uninstall      # remove the task

  No admin rights needed — the task runs as you, only when you're logged on.
#>
[CmdletBinding()]
param(
    [string]$Time = "09:00",
    [string]$TaskName = "PrivacyMirror",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$RunScript  = Join-Path $ProjectDir "runpass.py"

if ($Uninstall) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'." -ForegroundColor Green
    } else {
        Write-Host "No scheduled task named '$TaskName' found." -ForegroundColor Yellow
    }
    return
}

# Locate Python. Prefer pythonw.exe (no console window pops up on each run).
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) { throw "Could not find 'python' on PATH. Install Python or fix PATH first." }
$pythonExe = $pyCmd.Source
$pythonwExe = Join-Path (Split-Path $pythonExe -Parent) "pythonw.exe"
if (Test-Path $pythonwExe) { $exe = $pythonwExe } else { $exe = $pythonExe }

if (-not (Test-Path $RunScript)) { throw "runpass.py not found next to this script." }

Write-Host "Installing scheduled task '$TaskName'" -ForegroundColor Cyan
Write-Host "  Python : $exe"
Write-Host "  Script : $RunScript"
Write-Host "  When   : daily at $Time (and at logon catch-up if missed)"

$action  = New-ScheduledTaskAction -Execute $exe -Argument "`"$RunScript`"" -WorkingDirectory $ProjectDir
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

# Replace any existing definition with the same name.
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Runs one PrivacyMirror data-removal pass (sending + recurring re-removal)." | Out-Null

Write-Host "Done. The task will run daily at $Time." -ForegroundColor Green
Write-Host "Run it now to test:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove it later:     .\schedule-task.ps1 -Uninstall"
Write-Host "Check results in the dashboard's Recent activity, or in runpass.log."
