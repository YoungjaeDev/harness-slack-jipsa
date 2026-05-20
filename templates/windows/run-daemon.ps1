# Agent Bootstrap — Slack daemon 진입점 (Windows)
# 위치: $env:USERPROFILE\.claude\scripts\slack-jipsa\run-daemon.ps1
# Task Scheduler 가 -AtLogOn 으로 이 스크립트를 호출.
# .env 파싱 후 daemon.py 실행.

$ErrorActionPreference = "Stop"

$EnvFile = "$env:USERPROFILE\.claude\secrets\slack-jipsa.env"
if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing $EnvFile (모듈 1 시크릿 파일 작성 단계 먼저 진행)"
    exit 1
}

# .env 파싱 → 환경변수 (주석/빈 줄 skip)
Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*?)\s*=\s*(.*)\s*$') {
        Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
    }
}

# 로그 디렉토리
$LogDir = "$env:USERPROFILE\.claude\scripts\slack-jipsa\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "$(Get-Date -Format 'yyyy-MM-dd').log"

# Python 실행 (py launcher 우선, 폴백 python)
$PyExe = (Get-Command py -ErrorAction SilentlyContinue).Source
if (-not $PyExe) { $PyExe = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $PyExe) {
    Write-Error "Python 3.9+ 미설치 — 'winget install Python.Python.3.12' 또는 https://python.org"
    exit 1
}

$Daemon = "$env:USERPROFILE\.claude\scripts\slack-jipsa\daemon.py"
& $PyExe $Daemon *>> $Log
