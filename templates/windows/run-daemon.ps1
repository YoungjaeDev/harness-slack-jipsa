# Agent Bootstrap — Slack daemon 진입점 (Windows)
# 위치:
#   글로벌:    $env:USERPROFILE\.claude\scripts\slack-jipsa\run-daemon.ps1
#   프로젝트:  $env:USERPROFILE\.claude\scripts\slack-jipsa-{PROJECT_ID}\run-daemon.ps1
# Task Scheduler 가 -AtLogOn 으로 이 스크립트를 호출.
# .env 파싱 후 daemon.py 실행. 인스턴스 분리는 스크립트 위치 (부모 폴더명) 로 결정.

$ErrorActionPreference = "Stop"

# ── 인스턴스 결정 ───────────────────────────────────────────────────
# 우선순위: 환경변수 SLACK_JIPSA_INSTANCE > 스크립트 부모 폴더명 > "slack-jipsa".
if ($env:SLACK_JIPSA_INSTANCE) {
    $Instance = $env:SLACK_JIPSA_INSTANCE
} else {
    $instanceDir = Split-Path -Parent $PSCommandPath
    $Instance = if ($instanceDir) { Split-Path -Leaf $instanceDir } else { "slack-jipsa" }
}
if (-not $Instance) { $Instance = "slack-jipsa" }
$env:SLACK_JIPSA_INSTANCE = $Instance

$EnvFile = Join-Path $env:USERPROFILE ".claude\secrets\$Instance.env"
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Error "Missing $EnvFile (모듈 1 시크릿 파일 작성 단계 먼저 진행. Instance=$Instance)"
    exit 1
}

# .env 파싱 → 환경변수 (주석/빈 줄 skip)
Get-Content -LiteralPath $EnvFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*?)\s*=\s*(.*)\s*$') {
        Set-Item -Path "Env:$($matches[1])" -Value $matches[2]
    }
}

# 로그 디렉토리
$LogDir = Join-Path $env:USERPROFILE ".claude\scripts\$Instance\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "$(Get-Date -Format 'yyyy-MM-dd').log"

# Python 실행 (py launcher 우선, 폴백 python)
$PyExe = (Get-Command py -ErrorAction SilentlyContinue).Source
if (-not $PyExe) { $PyExe = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $PyExe) {
    Write-Error "Python 3.9+ 미설치 — 'winget install Python.Python.3.12' 또는 https://python.org"
    exit 1
}

$Daemon = Join-Path $env:USERPROFILE ".claude\scripts\$Instance\daemon.py"
# 사용자명에 한글/공백이 있어도 안전하도록 call operator + quoted path 사용.
& "$PyExe" "$Daemon" *>> "$Log"
