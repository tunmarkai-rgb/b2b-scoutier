# Runs the daily pipeline unattended. Called by the scheduled task (see register-task.ps1).
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
New-Item -ItemType Directory -Force (Join-Path $repo "logs") | Out-Null
$log = Join-Path $repo ("logs\run-" + (Get-Date -Format "yyyy-MM-dd_HHmm") + ".log")

"=== run-outreach started $(Get-Date -Format o) ===" | Out-File -FilePath $log -Encoding utf8
claude -p "/run-outreach" --permission-mode acceptEdits *>> $log
"=== finished $(Get-Date -Format o) exit=$LASTEXITCODE ===" | Out-File -FilePath $log -Append -Encoding utf8
