<#
.SYNOPSIS
    Cleanup: 폴더 트리거의 .processed/ 에서 90일 이상 된 파일 삭제.

.DESCRIPTION
    modules/02-folder-trigger.md 의 처리 완료 파일이 .processed/ 에 누적.
    주기적으로 정리 권장 (예: 월 1회 schtask).

.PARAMETER DaysOld
    이 일수 이상 된 파일 삭제. 기본 90.

.PARAMETER DryRun
    삭제 대상만 출력.

.EXAMPLE
    pwsh -File cleanup-processed.ps1
    pwsh -File cleanup-processed.ps1 -DaysOld 30 -DryRun
#>
param(
    [int]$DaysOld = 90,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$folderWatchRoot = Join-Path $env:USERPROFILE '.claude\scripts\folder-watch'
if (-not (Test-Path $folderWatchRoot)) {
    Write-Host "folder-watch 폴더 없음 — skip"
    exit 0
}

$processedDirs = Get-ChildItem -Path $folderWatchRoot -Directory -ErrorAction SilentlyContinue |
                 ForEach-Object { Join-Path $_.FullName '.processed' } |
                 Where-Object { Test-Path $_ }

if (-not $processedDirs) {
    Write-Host ".processed/ 폴더 없음 — skip"
    exit 0
}

$cutoff = (Get-Date).AddDays(-$DaysOld)
$deletedCount = 0

foreach ($dir in $processedDirs) {
    Get-ChildItem -Path $dir -File -ErrorAction SilentlyContinue |
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
