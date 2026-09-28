# Registers a daily Windows scheduled task that runs /run-outreach through Claude Code.
# Usage (PowerShell):  .\scheduler\register-task.ps1 [-Time "08:30"]
# Remove with:         Unregister-ScheduledTask -TaskName "B2B Scoutier - Run Outreach" -Confirm:$false
param([string]$Time = "08:30")

$script = Join-Path $PSScriptRoot "run-outreach.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
  -WorkingDirectory (Split-Path -Parent $PSScriptRoot)
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
  -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "B2B Scoutier - Run Outreach" -Action $action -Trigger $trigger `
  -Settings $settings -Description "Daily TUNMARK lead-gen pipeline (claude -p /run-outreach)" -Force
Write-Host "Scheduled daily at $Time. Logs go to logs\run-*.log"
