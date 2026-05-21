<#
.SYNOPSIS
    Stop hook (Windows): claude --print 세션 종료 시 슬랙 보고.

.DESCRIPTION
    sh 원본 (templates/hooks/slack-session-summary.sh) 의 PowerShell 검증본.
    핵심 흐름:
      1. 재귀 가드 (SLACK_HOOK_RUNNING)
      2. .env (~/.claude/secrets/slack-jipsa.env) 로드
      3. CLAUDE_SKIP_HOOKS=1 일 때 skip (daemon 호출 분리)
      4. stdin JSON 에서 session_id 추출
      5. ~/.claude/projects/ 에서 transcript .jsonl 검색
      6. 마지막 "진짜 user" 턴 이후의 assistant 텍스트 + tool 이름 수집
      7. mrkdwn 정리 + Slack post (webhook 우선, Bot Token 폴백)

    sh 원본의 노션 적재 (~L240-460) 는 본 PS 버전에서 생략.
    daemon 경로는 notion_logger.py 가 직접 적재. interactive claude 경로의
    노션 적재는 향후 별도 task 로 분리 가능.
#>

$ErrorActionPreference = 'Stop'

# ── 1) 재귀 가드 ────────────────────────────────────────────────────
if ($env:SLACK_HOOK_RUNNING -eq '1') { exit 0 }
$env:SLACK_HOOK_RUNNING = '1'

# CLAUDE_SKIP_HOOKS=1 (daemon 이 호출한 claude --print) 일 때 skip
if ($env:CLAUDE_SKIP_HOOKS -eq '1') { exit 0 }

# ── 2) stdin JSON 선읽기 → 인스턴스 매핑 → .env 로드 ────────────────
# stdin 은 한 번만 읽을 수 있으므로 여기서 먼저 받고 아래 4) 에서 재사용.
$STDIN_JSON = [Console]::In.ReadToEnd()

$stdinCwd = ''
if ($STDIN_JSON) {
    try {
        $stdinObj = $STDIN_JSON | ConvertFrom-Json
        if ($stdinObj.cwd) { $stdinCwd = [string]$stdinObj.cwd }
    } catch { }
}

# projects.json 의 등록 프로젝트 중 cwd 와 prefix match. 가장 긴 path → id.
# Windows 경로는 case-insensitive 이므로 양쪽 모두 lower-case 로 정규화 후 비교.
# StartsWith(string) 은 case-sensitive 라 그대로 두면 C:/Dev/Foo 와 c:/dev/foo 가 매칭 안 됨.
$instance = 'slack-jipsa'
$projectsJson = Join-Path $env:USERPROFILE '.claude\scripts\slack-jipsa-shared\projects.json'
if ($stdinCwd -and (Test-Path -LiteralPath $projectsJson)) {
    try {
        $projectsData = Get-Content -LiteralPath $projectsJson -Encoding UTF8 -Raw | ConvertFrom-Json
        $cwdNorm = ($stdinCwd -replace '\\', '/').ToLowerInvariant()
        $matched = @($projectsData.projects) |
            Where-Object { $_ -and $_.path -and $_.id } |
            Where-Object {
                $p = ($_.path -replace '\\', '/').ToLowerInvariant()
                ($cwdNorm -eq $p) -or $cwdNorm.StartsWith($p + '/')
            } |
            Sort-Object { ($_.path -replace '\\', '/').Length } -Descending |
            Select-Object -First 1
        if ($matched) {
            $instance = "slack-jipsa-$($matched.id)"
        }
    } catch { }
}

$envFile = Join-Path $env:USERPROFILE ".claude\secrets\$instance.env"
if (-not (Test-Path -LiteralPath $envFile)) {
    # 프로젝트 인스턴스 .env 가 없으면 글로벌로 폴백 (호환성).
    $envFile = Join-Path $env:USERPROFILE '.claude\secrets\slack-jipsa.env'
}
if (-not (Test-Path -LiteralPath $envFile)) { exit 0 }

Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#')) { return }
    if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
        $name = $Matches[1]
        $value = $Matches[2].Trim().Trim('"').Trim("'")
        Set-Item -Path "env:$name" -Value $value
    }
}

$slackUrl = $env:SLACK_SESSION_WEBHOOK
$botToken = $env:SLACK_BOT_TOKEN
$channel  = $env:SLACK_CHANNEL
$userName = if ($env:USER_NAME) { $env:USER_NAME } else { '사용자' }

# webhook · Bot Token 둘 다 없으면 조용히 종료
if (-not $slackUrl -and (-not $botToken -or -not $channel)) { exit 0 }

# ── 3) stdin JSON 파싱 (위 2 에서 이미 읽음, 재사용) ────────────────
if (-not $STDIN_JSON) { exit 0 }

try {
    $stdinObj = $STDIN_JSON | ConvertFrom-Json
    $sessionId = $stdinObj.session_id
    $cwd = if ($stdinCwd) { $stdinCwd } else { $stdinObj.cwd }
} catch {
    exit 0
}
if (-not $sessionId) { exit 0 }
if (-not $cwd) { $cwd = (Get-Location).Path }

# ── 4) transcript .jsonl 검색 ───────────────────────────────────────
$projectsDir = Join-Path $env:USERPROFILE '.claude\projects'
if (-not (Test-Path $projectsDir)) { exit 0 }

$transcript = Get-ChildItem -Path $projectsDir -Filter "$sessionId.jsonl" -Recurse -ErrorAction SilentlyContinue |
              Select-Object -First 1
if (-not $transcript) { exit 0 }

# ── 5) JSONL 파싱 + 마지막 진짜 user 턴 찾기 ────────────────────────
$entries = Get-Content $transcript.FullName -Encoding UTF8 |
           Where-Object { $_ } |
           ForEach-Object {
               try { $_ | ConvertFrom-Json } catch { $null }
           } |
           Where-Object { $_ }

function Get-TextContent {
    param($content)
    if ($null -eq $content) { return '' }
    if ($content -is [string]) { return $content }
    if ($content -is [System.Array] -or $content -is [System.Collections.IEnumerable]) {
        $texts = @()
        foreach ($item in $content) {
            if ($item.type -eq 'text' -and $item.text) {
                $texts += $item.text
            }
        }
        return ($texts -join "`n")
    }
    return ''
}

function Test-RealUser {
    param($entry)
    if ($entry.type -ne 'user') { return $false }
    if (-not $entry.message) { return $false }
    $txt = Get-TextContent $entry.message.content
    $trimmed = $txt -replace '\s', ''
    if (-not $trimmed) { return $false }
    if ($txt -match '^\s*<task-notification>') { return $false }
    return $true
}

# 마지막 real_user 인덱스 찾기
$lastRealUserIdx = -1
for ($i = 0; $i -lt $entries.Count; $i++) {
    if (Test-RealUser $entries[$i]) {
        $lastRealUserIdx = $i
    }
}
if ($lastRealUserIdx -lt 0) { exit 0 }

$turn = $entries[$lastRealUserIdx..($entries.Count - 1)]

# ── 6) user 텍스트 + assistant 텍스트 + tool 이름 수집 ──────────────
$userPromptFull = Get-TextContent $turn[0].message.content

$assistantTexts = @()
$toolNames = @()
$modelsUsed = @()

foreach ($entry in $turn) {
    if ($entry.type -ne 'assistant') { continue }
    if (-not $entry.message) { continue }
    if ($entry.message.model) { $modelsUsed += $entry.message.model }
    $content = $entry.message.content
    if ($null -eq $content) { continue }
    if ($content -is [string]) {
        if ($content.Trim()) { $assistantTexts += $content }
    } elseif ($content -is [System.Array] -or $content -is [System.Collections.IEnumerable]) {
        foreach ($block in $content) {
            if ($block.type -eq 'text' -and $block.text) {
                $assistantTexts += $block.text
            } elseif ($block.type -eq 'tool_use' -and $block.name) {
                $toolNames += $block.name
            }
        }
    }
}

$assistantTextAll = $assistantTexts -join "`n`n"
$assistantTextLast = if ($assistantTexts.Count -gt 0) { $assistantTexts[-1] } else { '' }

# 도구 이름 집계 (등장 순서 유지, 동일 도구 x N)
function Format-ToolNames {
    param([string[]]$names)
    if (-not $names -or $names.Count -eq 0) { return '(도구 없음)' }
    $order = @()
    $counts = @{}
    foreach ($n in $names) {
        if (-not $counts.ContainsKey($n)) {
            $order += $n
            $counts[$n] = 1
        } else {
            $counts[$n]++
        }
    }
    ($order | ForEach-Object {
        if ($counts[$_] -eq 1) { $_ } else { "$_ x$($counts[$_])" }
    }) -join ', '
}
$actionsMd = Format-ToolNames $toolNames

# 모델 요약
$modelShort = 'unknown'
if ($modelsUsed.Count -gt 0) {
    $topModel = ($modelsUsed | Group-Object | Sort-Object Count -Descending | Select-Object -First 1).Name
    $modelShort = switch -Regex ($topModel) {
        '^claude-opus' { 'opus' }
        '^claude-sonnet' { 'sonnet' }
        '^claude-haiku' { 'haiku' }
        default { $topModel }
    }
}

# ── 7) mrkdwn 정리 (**bold** → *bold*, [text](url) → <url|text>) ────
function ConvertTo-SlackMrkdwn {
    param([string]$text)
    if (-not $text) { return '' }
    $out = $text
    # **bold** → *bold*
    $out = $out -replace '\*\*([^*\n]+)\*\*', '*$1*'
    # [text](url) → <url|text>
    $out = [regex]::Replace($out, '\[([^\]]+)\]\(([^)]+)\)', '<$2|$1>')
    return $out
}

# ── 8) Slack 메시지 본문 + 전송 ─────────────────────────────────────
function Limit-Length {
    param([string]$s, [int]$max = 1900)
    if (-not $s) { return '' }
    if ($s.Length -gt $max) { return $s.Substring(0, $max) + '…' }
    return $s
}

$projectName = Split-Path $cwd -Leaf
$taskShort = Limit-Length $userPromptFull 200
$resultMrkdwn = ConvertTo-SlackMrkdwn $assistantTextLast
$resultShort = Limit-Length $resultMrkdwn 1500

$payloadText = @"
*세션 요약* — $projectName ($modelShort)

*${userName}님 요청*
> $taskShort

*수행 내역*
$actionsMd

*결과*
$resultShort
"@

function Send-Slack {
    param([string]$text)
    $body = @{ text = $text }
    if ($channel) { $body['channel'] = $channel }
    $bodyJson = $body | ConvertTo-Json -Depth 10 -Compress

    if ($slackUrl) {
        try {
            Invoke-RestMethod -Uri $slackUrl -Method Post -Body $bodyJson `
                -ContentType 'application/json; charset=utf-8' | Out-Null
            return $true
        } catch {
            Write-Warning "webhook failed: $_"
        }
    }
    if ($botToken -and $channel) {
        try {
            $body['channel'] = $channel
            $bodyJson = $body | ConvertTo-Json -Depth 10 -Compress
            Invoke-RestMethod -Uri 'https://slack.com/api/chat.postMessage' `
                -Method Post -Body $bodyJson `
                -ContentType 'application/json; charset=utf-8' `
                -Headers @{ Authorization = "Bearer $botToken" } | Out-Null
            return $true
        } catch {
            Write-Warning "chat.postMessage failed: $_"
        }
    }
    return $false
}

[void](Send-Slack $payloadText)

exit 0
