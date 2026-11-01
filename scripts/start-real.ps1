<#
.SYNOPSIS
  Starts the whole REAL stack with one command: MongoDB, public address, backend, frontend.
  Real Meta (ads, organic posts, DMs), real AI text, real images. Ads can SPEND REAL MONEY.

.PARAMETER Images   Image provider: gemini (default) | openai | ai (free service) | fake (placeholder)
.PARAMETER Llm      Text AI: gemini (default, GEMINI_API_KEY) | openrouter (OPENROUTER_API_KEY) | litellm (OPENAI_API_KEY)
.PARAMETER Family   With -Llm openrouter: which models OpenRouter serves, gemini (default) | openai
.PARAMETER PublicUrl  HTTPS address of YOUR OWN tunnel that forwards to port 3000 (the frontend), for example a
                      Dev Tunnels / ngrok address. Needed when the Meta app is Live or other people connect:
                      Facebook login, images and the DM webhook then all run through this one address.
                      Without it a throwaway cloudflared tunnel is used and login stays on http://localhost:3000
                      (that only works while the Meta app is in Development mode). Default: $env:ADCRAFT_PUBLIC_URL
.PARAMETER TunnelId   With -PublicUrl: a Dev Tunnels id for this script to host (devtunnel host <id>). Leave empty
                      if the tunnel is already running (for example VS Code port forwarding).
.PARAMETER MaxDailyBudgetInr  Safety cap on one campaign's daily budget (default 150)
.PARAMETER VerifyToken  Webhook verify token to type into the Meta app (default verify-123)
.PARAMETER DryRun   Print what would run and start nothing
.PARAMETER Prod     Build and serve the frontend in production mode (enabled automatically with -PublicUrl)

Meta app id, secret and login configuration come from .env. Stop everything with .\scripts\stop-real.ps1
#>
param(
    [ValidateSet("gemini", "openai", "ai", "fake")][string]$Images = "gemini",
    [ValidateSet("gemini", "openrouter", "litellm")][string]$Llm = "gemini",
    [ValidateSet("gemini", "openai")][string]$Family = "gemini",
    [string]$PublicUrl = $env:ADCRAFT_PUBLIC_URL,
    [string]$PublicImageUrl = "",
    [string]$TunnelId = "",
    [int]$MaxDailyBudgetInr = 150,
    [string]$VerifyToken = "verify-123",
    [switch]$DryRun,
    [switch]$Prod
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$statePath = Join-Path $env:TEMP "adcraft-real-run.json"
$db = "mongodb://localhost:27117/?directConnection=true"

$PublicUrl = "$PublicUrl".Trim().TrimEnd("/")
$PublicImageUrl = "$PublicImageUrl".Trim().TrimEnd("/")
$useProd = $Prod -or [bool]$PublicUrl
if ($PublicUrl -and $PublicUrl -notmatch "^https://[^/]+$") { throw "-PublicUrl must look like https://name.example.com (no path)" }

function Step($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function PortInUse($port) { [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }
function WaitFor($url, $seconds) {
    for ($i = 0; $i -lt $seconds; $i++) {
        try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 | Out-Null; return $true } catch { Start-Sleep 1 }
    }
    return $false
}

function Get-CloudflaredExe {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $local = Join-Path $PSScriptRoot "cloudflared.exe"
    if (Test-Path $local) { return $local }
    Write-Host "Downloading cloudflared (needed for Meta to fetch images without anti-phishing blocks)..." -ForegroundColor Yellow
    $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Invoke-WebRequest -Uri $url -OutFile $local -TimeoutSec 60
    return $local
}

$tunnelPlan = if ($PublicUrl) {
    "Your own tunnel $PublicUrl (must forward to port 3000); Facebook login returns to $PublicUrl/api/meta/callback"
} else {
    "Throwaway public tunnel (cloudflared) to the backend; Facebook login stays on http://localhost:3000"
}
$plan = @(
    "MongoDB container acm-dev-mongo on port 27117 (replica set)",
    $tunnelPlan,
    "Backend on http://localhost:8000: META_MODE=real, text=$Llm, images=$Images, caps: Rs $MaxDailyBudgetInr per day, 1 day",
    "Frontend on http://localhost:3000"
)
if ($DryRun) { Write-Host "DRY RUN, nothing is started:"; $plan | ForEach-Object { Write-Host " - $_" }; return }

if (Test-Path $statePath) { throw "A real run is already started. Run .\scripts\stop-real.ps1 first." }
foreach ($port in 8000, 3000) { if (PortInUse $port) { throw "Port $port is already in use. Close that program first." } }

Step "1/4 MongoDB"
$existing = docker ps -a --format "{{.Names}}"
if ($existing -notcontains "acm-dev-mongo") {
    docker run -d --name acm-dev-mongo -p 27117:27017 -v acm-dev-mongo-data:/data/db mongo:8 --replSet rs0 --bind_ip_all | Out-Null
    Start-Sleep 6
    docker exec acm-dev-mongo mongosh --quiet --eval "rs.initiate({_id:'rs0',members:[{_id:0,host:'localhost:27017'}]})" | Out-Null
} else {
    docker start acm-dev-mongo | Out-Null
}
$ready = $false
for ($i = 0; $i -lt 40 -and -not $ready; $i++) {
    $answer = docker exec acm-dev-mongo mongosh --quiet --eval "db.hello().isWritablePrimary" 2>$null
    if ("$answer" -match "true") { $ready = $true } else { Start-Sleep 1 }
}
if (-not $ready) { throw "MongoDB did not become ready. Is Docker Desktop running (and not paused)?" }
Write-Host "MongoDB is a writable primary."

Step "2/4 Public address"
$tunnel = $null
$imageTunnel = $null
$imageAddress = $null

if ($PublicUrl) {
    if ($TunnelId) {
        $devtunnel = (Get-Command devtunnel -ErrorAction Stop).Source
        $tunnel = Start-Process -FilePath $devtunnel -ArgumentList "host", $TunnelId -WindowStyle Hidden -PassThru
        Write-Host "Hosting Dev Tunnel $TunnelId"
    }
    $appUrl = $PublicUrl
    Write-Host "Using your tunnel: $PublicUrl (it must forward to port 3000)"

    # Microsoft Dev Tunnels and ngrok-free serve an HTML anti-phishing / browser warning interstitial
    # on GET requests with Accept: text/html, which causes Meta's image crawler to fail with
    # "The media could not be fetched from this URI".
    # We serve images via a dedicated cloudflared tunnel to bypass the warning page.
    if ($PublicImageUrl) {
        $imageAddress = $PublicImageUrl
        Write-Host "Using specified public image address: $imageAddress"
    } elseif ($PublicUrl -match "devtunnels\.ms|ngrok") {
        try {
            $cloudflared = Get-CloudflaredExe
            $imgLog = Join-Path $env:TEMP "adcraft-image-tunnel.log"
            Remove-Item $imgLog, "$imgLog.out" -ErrorAction SilentlyContinue
            $imageTunnel = Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--url", "http://localhost:8000" `
                -RedirectStandardError $imgLog -RedirectStandardOutput "$imgLog.out" -WindowStyle Hidden -PassThru
            for ($i = 0; $i -lt 45 -and -not $imageAddress; $i++) {
                Start-Sleep 1
                if (Test-Path $imgLog) {
                    $hit = Select-String -Path $imgLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
                    if ($hit) { $imageAddress = $hit.Matches[0].Value }
                }
            }
            if ($imageAddress) {
                Write-Host "Image tunnel (Cloudflare, bypasses Dev Tunnels anti-phishing screen): $imageAddress" -ForegroundColor Green
            } else {
                Write-Warning "Could not obtain Cloudflare tunnel for images. Falling back to $PublicUrl/api"
                $imageAddress = "$PublicUrl/api"
            }
        } catch {
            Write-Warning "cloudflared failed ($($_.Exception.Message)). Falling back to $PublicUrl/api"
            $imageAddress = "$PublicUrl/api"
        }
    } else {
        $imageAddress = "$PublicUrl/api"
    }
} else {
    $log = Join-Path $env:TEMP "adcraft-tunnel.log"
    Remove-Item $log, "$log.out" -ErrorAction SilentlyContinue
    $cloudflared = Get-CloudflaredExe
    $tunnel = Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--url", "http://localhost:8000" `
        -RedirectStandardError $log -RedirectStandardOutput "$log.out" -WindowStyle Hidden -PassThru
    $quick = $null
    for ($i = 0; $i -lt 45 -and -not $quick; $i++) {
        Start-Sleep 1
        if (Test-Path $log) {
            $hit = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { $quick = $hit.Matches[0].Value }
        }
    }
    if (-not $quick) { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue; throw "The tunnel gave no address. See $log" }
    $appUrl = "http://localhost:3000"
    $imageAddress = $quick
    Write-Host "Public address (backend only): $quick"
}

# Everything the backend needs. Meta app id / secret / login configuration come from .env.
$env:MONGODB_URI = $db
$env:META_MODE = "real"
$env:LLM_PROVIDER = $Llm
$env:OPENROUTER_MODEL_FAMILY = $Family
$env:IMAGE_PROVIDER = $Images
$env:ALLOW_REAL_AD_SPEND = "true"
$env:SAFE_MODE_NO_SPEND = "false"
$env:MAX_DAILY_BUDGET_INR = "$MaxDailyBudgetInr"
$env:MAX_CAMPAIGN_DAYS = "1"
$env:ALLOW_ORGANIC_PUBLISH = "true"
$env:META_WEBHOOK_VERIFY_TOKEN = $VerifyToken
if ($PublicUrl) {
    # One address for app, OAuth redirect and webhook:
    $env:META_REDIRECT_URI = "$PublicUrl/api/meta/callback"
    $env:PUBLIC_BASE_URL = $imageAddress
    $env:ALLOWED_DEV_ORIGINS = ([uri]$PublicUrl).Host
    $webhookUrl = "$PublicUrl/api/webhooks/instagram"
} else {
    $env:PUBLIC_BASE_URL = $imageAddress
    $webhookUrl = "$imageAddress/webhooks/instagram"
}
Remove-Item Env:FAKE_META_FAIL_AT -ErrorAction SilentlyContinue

Step "3/4 Backend"
$api = Start-Process powershell -WorkingDirectory $backend -PassThru `
    -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle='AdCraft backend (REAL)'; uv run uvicorn app.main:app --port 8000"
if (-not (WaitFor "http://127.0.0.1:8000/health" 120)) { throw "Backend did not start. Look at the 'AdCraft backend (REAL)' window." }
Write-Host "Backend is up."

Step "4/4 Frontend"
$frontendCommand = if ($useProd) { "npm run build; if (`$LASTEXITCODE -eq 0) { npm start }" } else { "npm run dev" }
$web = Start-Process powershell -WorkingDirectory $frontend -PassThru `
    -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle='AdCraft frontend'; $frontendCommand"
$frontendWait = if ($useProd) { 600 } else { 120 }   # a production build can take several minutes
if (-not (WaitFor "http://localhost:3000" $frontendWait)) { throw "Frontend did not start. Look at the 'AdCraft frontend' window." }

if ($PublicUrl) {
    if (WaitFor "$PublicUrl/api/health" 60) { Write-Host "Your public address reaches the app and the backend." }
    else { Write-Warning "$PublicUrl does not reach the app. Is the tunnel running, public (anonymous) and forwarding port 3000?" }
}

$tunnelPid = if ($tunnel) { $tunnel.Id } else { $null }
$imageTunnelPid = if ($imageTunnel) { $imageTunnel.Id } else { $null }
@{ tunnel = $tunnelPid; imageTunnel = $imageTunnelPid; backend = $api.Id; frontend = $web.Id; url = $appUrl; imageUrl = $imageAddress } | ConvertTo-Json | Set-Content $statePath
Start-Process $appUrl

Write-Host ""
Write-Host "REAL STACK IS RUNNING" -ForegroundColor Green
Write-Host "  Open the app at:   $appUrl" -ForegroundColor Green
if ($PublicUrl) {
    Write-Host "                     (use THIS address, not localhost; other people open it too)"
    Write-Host "  Meta must have:    App domain  $(([uri]$PublicUrl).Host)"
    Write-Host "                     Redirect URI  $PublicUrl/api/meta/callback"
}
Write-Host "  Public images:     $imageAddress (bypasses Dev Tunnels anti-phishing screen)"
Write-Host "  DM webhook URL:    $webhookUrl"
Write-Host "  Webhook verify:    $VerifyToken"
Write-Host "  Text AI / images:  $Llm / $Images"
Write-Host "  Caps:              Rs $MaxDailyBudgetInr per day, 1 day. Ads and organic posts are REAL."
Write-Host "  Stop everything:   .\scripts\stop-real.ps1"
