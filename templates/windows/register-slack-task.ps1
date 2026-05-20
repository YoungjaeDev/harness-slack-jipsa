# Agent Bootstrap — Slack daemon 자동 시작 등록 (Task Scheduler)
# 실행: powershell -ExecutionPolicy Bypass -File register-slack-task.ps1
# 관리자 권한 불필요 (current user task).

$TaskName = "AgentBootstrap-SlackDaemon"
$ScriptPath = "$env:USERPROFILE\.claude\scripts\slack-jipsa\run-daemon.ps1"

if (-not (Test-Path $ScriptPath)) {
    Write-Error "Missing $ScriptPath — 모듈 1 run-daemon.ps1 카피 단계 먼저 진행"
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
