<#
.SYNOPSIS
    Cleanup: 30일 이상 된 로그 파일 삭제.

.DESCRIPTION
    daemon.log 의 TimedRotatingFileHandler 는 30일 자동 회전하지만,
    folder-watch 의 일별 로그 등 다른 디렉토리는 외부 cleanup 필요.

.PARAMETER DaysOld
    이 일수 이상 된 파일 삭제. 기본 30.

.PARAMETER DryRun
    삭제 대상만 출력. 실제 삭제 안 함.

.EXAMPLE
    pwsh -File cleanup-old-logs.ps1
    pwsh -File cleanup-old-logs.ps1 -DaysOld 60 -DryRun
#>
param(
    [int]$DaysOld = 30,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$logDirs = @(
    (Join-Path $env:USERPROFILE '.claude\scripts\slack-jipsa\logs'),
    (Join-Path $env:USERPROFILE '.claude\scripts\folder-watch\logs')
)
$cutoff = (Get-Date).AddDays(-$DaysOld)

$deletedCount = 0
foreach ($dir in $logDirs) {
    if (-not (Test-Path $dir)) { continue }
    Get-ChildItem -Path $dir -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        ForEach-Object {
            if ($DryRun) {
                Write-Host "[DRY] would delete: $($_.FullName)"
            } else {
                try {
                    Remove-Item -LiteralPath $_.FullName -Force
                    Write-Host "deleted: $($_.FullName)"
                    $deletedCount++
                } catch {
                    Write-Warning "delete failed: $($_.FullName) - $_"
                }
            }
        }
}

if (-not $DryRun) {
    Write-Host "총 $deletedCount 개 파일 삭제."
}
