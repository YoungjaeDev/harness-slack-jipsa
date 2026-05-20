# Agent Bootstrap — Folder watcher 자동 시작 등록 (Task Scheduler)
# 실행: powershell -ExecutionPolicy Bypass -File register-folder-task.ps1
# 관리자 권한 불필요.

$TaskName = "AgentBootstrap-FolderWatch"
$ScriptPath = "$env:USERPROFILE\.claude\scripts\folder-watch\folder-watch.ps1"

if (-not (Test-Path $ScriptPath)) {
    Write-Error "Missing $ScriptPath — 모듈 2 folder-watch.ps1 카피·치환 먼저 진행"
    exit 1
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Task '$TaskName' 등록 완료. State=$((Get-ScheduledTask $TaskName).State)"
