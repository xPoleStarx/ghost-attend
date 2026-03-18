# GhostAttend - Setup Script for Windows (PowerShell)

Write-Host "GhostAttend Windows Kurulumuna Hos Geldiniz!" -ForegroundColor Cyan
Write-Host "---------------------------------------"

# 1. Gerekli araclari kontrol et
try {
    $dockerVersion = docker --version | Out-Null
} catch {
    Write-Error "Hata: docker yuklu degil veya PATH'e eklenmemis. Kurulum iptal edildi."
    exit 1
}

try {
    $composeVersion = docker compose version | Out-Null
} catch {
    Write-Error "Hata: docker compose yuklu degil. Kurulum iptal edildi."
    exit 1
}

$ComposeFile = "docker-compose.dev.yml"
$ComposeArgs = @("compose", "-f", $ComposeFile)

function Set-EnvValue {
    param(
        [string]$Key,
        [string]$Value
    )

    (Get-Content ".env") -replace "^$Key=.*", "$Key=$Value" | Set-Content ".env"
}

# 2. .env Dosyasinin Olusturulmasi
if (-not (Test-Path ".env")) {
    Write-Host ".env.example kopyalanarak .env dosyasi olusturuluyor..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
} else {
    Write-Host ".env dosyasi zaten mevcut." -ForegroundColor Green
}

# 3. Etkilesimli .env Ayarlari
Write-Host "`nBot ve API Ayarlari" -ForegroundColor Cyan
Write-Host "Bu asamada botunuzun calismasi icin gereken temel anahtarlari gireceksiniz."
Write-Host "Eger onceden .env dosyanizi ayarladiysaniz bu adimlari Enter'a basarak gecebilirsiniz.`n"

$tgToken = Read-Host "Telegram Bot Token'inizi giriniz"
if (![string]::IsNullOrEmpty($tgToken)) {
    Set-EnvValue "TELEGRAM_BOT_TOKEN" $tgToken
}

Write-Host "`nHangi yapay zeka saglayicisini kullanmak istersiniz?"
Write-Host "1) Google (Gemini - Onerilen/Ucretsiz)"
Write-Host "2) OpenAI (GPT)"
Write-Host "3) Anthropic (Claude)"
$providerChoice = Read-Host "Seciminiz (1/2/3) [Varsayilan: 1]"

$provider = "google"
$targetKeyVar = "GOOGLE_API_KEY"
if ($providerChoice -eq "2") {
    $provider = "openai"
    $targetKeyVar = "OPENAI_API_KEY"
} elseif ($providerChoice -eq "3") {
    $provider = "anthropic"
    $targetKeyVar = "ANTHROPIC_API_KEY"
}

Set-EnvValue "AGENT_LLM_PROVIDER" $provider

$apiKey = Read-Host "$provider API Key'inizi giriniz"
if (![string]::IsNullOrEmpty($apiKey)) {
    Set-EnvValue $targetKeyVar $apiKey
}

# 4. Sifrelerin ve Anahtarlarin Otomatik Uretimi
Write-Host "`nGuvenlik ve Veritabani sifreleri otomatik denetleniyor..." -ForegroundColor Yellow

function Get-RandomString($length) {
    $bytes = New-Object byte[] $length
    $rnd = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rnd.GetBytes($bytes)
    $rnd.Dispose()
    return [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_').Replace('=', '')
}

$envContent = Get-Content ".env"
if ($envContent -match "^MASTER_ENCRYPTION_KEY=\s*(#.*)?$") {
    $newKey = Get-RandomString 32
    Set-EnvValue "MASTER_ENCRYPTION_KEY" $newKey
}
if ($envContent -match "^POSTGRES_USER=\s*$") {
    Set-EnvValue "POSTGRES_USER" "ghost_admin"
}
if ($envContent -match "^POSTGRES_PASSWORD=\s*$") {
    $pgPass = Get-RandomString 16
    Set-EnvValue "POSTGRES_PASSWORD" $pgPass
}
if ($envContent -match "^REDIS_PASSWORD=\s*$") {
    $rdPass = Get-RandomString 16
    Set-EnvValue "REDIS_PASSWORD" $rdPass
}

$envMap = @{}
Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') {
        return
    }
    $parts = $_ -split '=', 2
    $envMap[$parts[0]] = $parts[1]
}

Set-EnvValue "ENVIRONMENT" "development"
Set-EnvValue "DATABASE_URL" "postgresql+asyncpg://$($envMap.POSTGRES_USER):$($envMap.POSTGRES_PASSWORD)@$($envMap.POSTGRES_HOST):$($envMap.POSTGRES_PORT)/$($envMap.POSTGRES_DB)"
Set-EnvValue "REDIS_URL" "redis://:$($envMap.REDIS_PASSWORD)@$($envMap.REDIS_HOST):$($envMap.REDIS_PORT)/0"

# 5. Host Klasorlerinin Ayarlanmasi
Write-Host "Gerekli klasorler olusturuluyor..." -ForegroundColor Yellow
$folders = @("logs", "screenshots", "certs", "backups", "data")
foreach ($folder in $folders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Force -Path $folder | Out-Null
    }
}

Write-Host "---------------------------------------"
Write-Host "Kurulum basariyla tamamlandi!" -ForegroundColor Green
Write-Host ""

$startNow = Read-Host "Sistemi simdi baslatmak ister misiniz? (Y/n)"
if ([string]::IsNullOrEmpty($startNow) -or $startNow -match "^[Yy]$") {
    Write-Host "Docker Compose ile sistem baslatiliyor..." -ForegroundColor Cyan
    docker @ComposeArgs up -d --build

    Write-Host "Sistem baslatildi! Sonraki kullanim icin: .\scripts\dev.ps1 logs" -ForegroundColor Green
} else {
    Write-Host "Kurulum tamamlandi. Istediginiz zaman '.\scripts\dev.ps1 up' ile baslatabilirsiniz."
}
Write-Host "Iyi dersler!" -ForegroundColor Yellow
