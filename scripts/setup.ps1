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

# 3. Master Encryption Key Uretimi
$envContent = Get-Content ".env"
if ($envContent -match "MASTER_ENCRYPTION_KEY=your-32-byte-base64-key-here") {
    Write-Host "Guvenli Master Encryption Key uretiliyor..." -ForegroundColor Yellow
    
    $bytes = New-Object byte[] 32
    $rnd = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rnd.GetBytes($bytes)
    $rnd.Dispose()
    
    $newKey = [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_').Replace('=', '')
    
    (Get-Content ".env") -replace "MASTER_ENCRYPTION_KEY=your-32-byte-base64-key-here", "MASTER_ENCRYPTION_KEY=$newKey" | Set-Content ".env"
    
    Write-Host "Basari: .env dosyasina yeni key eklendi." -ForegroundColor Green
}

# 4. Host Klasorlerinin Ayarlanmasi
Write-Host "Gerekli klasorler olusturuluyor..." -ForegroundColor Yellow
$folders = @("logs", "screenshots", "certs", "backups")
foreach ($folder in $folders) {
    if (-not (Test-Path $folder)) {
        New-Item -ItemType Directory -Force -Path $folder | Out-Null
    }
}

Write-Host "---------------------------------------"
Write-Host "Kurulumun ilk asamasi tamamlandi!" -ForegroundColor Green
Write-Host ""
Write-Host "SONRAKI ADIMLAR:" -ForegroundColor Cyan
Write-Host "1. '.env' dosyasini acin"
Write-Host "2. TELEGRAM_BOT_TOKEN ve ilgili LLM API (Google/OpenAI/Anthropic) anahtarini ekleyin."
Write-Host "3. Sistemi baslatmak icin su komutu calistirin:"
Write-Host "   docker compose up -d"
Write-Host ""
Write-Host "Veritabani tablolari otomatik olarak olusturulacaktir."
Write-Host "Iyi dersler!" -ForegroundColor Yellow
