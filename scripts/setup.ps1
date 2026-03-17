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
    (Get-Content ".env") -replace "^TELEGRAM_BOT_TOKEN=.*", "TELEGRAM_BOT_TOKEN=$tgToken" | Set-Content ".env"
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

(Get-Content ".env") -replace "^AGENT_LLM_PROVIDER=.*", "AGENT_LLM_PROVIDER=$provider" | Set-Content ".env"

$apiKey = Read-Host "$provider API Key'inizi giriniz"
if (![string]::IsNullOrEmpty($apiKey)) {
    (Get-Content ".env") -replace "^$targetKeyVar=.*", "$targetKeyVar=$apiKey" | Set-Content ".env"
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
    (Get-Content ".env") -replace "^MASTER_ENCRYPTION_KEY=.*", "MASTER_ENCRYPTION_KEY=$newKey" | Set-Content ".env"
}
if ($envContent -match "^POSTGRES_USER=\s*$") {
    (Get-Content ".env") -replace "^POSTGRES_USER=.*", "POSTGRES_USER=ghost_admin" | Set-Content ".env"
}
if ($envContent -match "^POSTGRES_PASSWORD=\s*$") {
    $pgPass = Get-RandomString 16
    (Get-Content ".env") -replace "^POSTGRES_PASSWORD=.*", "POSTGRES_PASSWORD=$pgPass" | Set-Content ".env"
}
if ($envContent -match "^REDIS_PASSWORD=\s*$") {
    $rdPass = Get-RandomString 16
    (Get-Content ".env") -replace "^REDIS_PASSWORD=.*", "REDIS_PASSWORD=$rdPass" | Set-Content ".env"
}

# 5. Host Klasorlerinin Ayarlanmasi
Write-Host "Gerekli klasorler olusturuluyor..." -ForegroundColor Yellow
$folders = @("logs", "screenshots", "certs", "backups")
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

    # Once DB + Redis are healthy, run migrations once, then start all services.
    Write-Host "PostgreSQL ve Redis baslatiliyor..." -ForegroundColor Cyan
    docker compose up -d postgres redis

    Write-Host "Veritabaninin hazir olmasi bekleniyor..." -ForegroundColor Cyan
    Start-Sleep -Seconds 5

    Write-Host "Alembic migration'lari calistiriliyor (upgrade head)..." -ForegroundColor Cyan
    docker compose run --rm bot alembic upgrade head

    Write-Host "Tum servisler baslatiliyor..." -ForegroundColor Cyan
    docker compose up -d

    Write-Host "Sistem baslatildi! Loglari gormek icin: docker compose logs -f bot" -ForegroundColor Green
} else {
    Write-Host "Kurulum tamamlandi. Istediginiz zaman 'docker compose up -d' ile baslatabilirsiniz."
}
Write-Host "Iyi dersler!" -ForegroundColor Yellow
