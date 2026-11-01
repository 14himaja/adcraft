param(
    [string]$Container = "acm-dev-mongo",
    [string]$Output = (Join-Path (Get-Location) ("acm-backup-{0}.archive" -f (Get-Date -Format "yyyyMMdd-HHmmss")))
)
$ErrorActionPreference = "Stop"
$containerArchive = "/tmp/acm-backup-$([guid]::NewGuid().ToString('N')).archive"
try {
    docker exec $Container mongodump --db acm "--archive=$containerArchive"
    if ($LASTEXITCODE -ne 0) { throw "mongodump failed with exit code $LASTEXITCODE" }
    docker cp "${Container}:$containerArchive" $Output
    if ($LASTEXITCODE -ne 0) { throw "docker cp failed with exit code $LASTEXITCODE" }
} finally {
    docker exec $Container rm -f $containerArchive 2>$null | Out-Null
}
if (-not (Test-Path -LiteralPath $Output)) { throw "Backup was not written to $Output" }
Write-Host "Database backup written to $Output"
