<#
.SYNOPSIS
  Stops what start-real.ps1 started: tunnel, backend, frontend. Real spending and posting end with the backend.

.PARAMETER StopDb  Also stop the MongoDB container (its data is kept)
#>
param([switch]$StopDb)

$statePath = Join-Path $env:TEMP "adcraft-real-run.json"

if (Test-Path $statePath) {
    $state = Get-Content $statePath -Raw | ConvertFrom-Json
    foreach ($name in "frontend", "backend", "tunnel", "imageTunnel") {
        $processId = $state.$name
        if ($processId -and (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
            taskkill /PID $processId /T /F | Out-Null   # the window and everything it started
            Write-Host "Stopped $name (pid $processId)"
        } elseif (($name -eq "tunnel" -or $name -eq "imageTunnel") -and -not $processId) {
            Write-Host "$name`: yours (not started by the script), left running"
        } else {
            Write-Host "$name was not running"
        }
    }
    Remove-Item $statePath -ErrorAction SilentlyContinue
} else {
    Write-Host "No real run is recorded. Nothing to stop."
}

if ($StopDb) {
    docker stop acm-dev-mongo | Out-Null
    Write-Host "Stopped MongoDB container acm-dev-mongo (data kept)"
}

Write-Host "Done. The real-spend and real-posting switches existed only inside the backend process, so they are off now."
