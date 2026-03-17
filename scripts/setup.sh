#!/bin/bash
# GhostAttend — Automatic Setup Script
# Bu script, projeyi klonlayan kullanıcının kurulumunu "tek tık" seviyesine indirir.

set -e

echo "👻 GhostAttend Kurulumuna Hoş Geldiniz!"
echo "---------------------------------------"

# 1. Gerekli araçların kontrolü
command -v docker >/dev/null 2>&1 || { echo >&2 "❌ Hata: docker yüklü değil. Kurulum iptal edildi."; exit 1; }
command -v docker compose >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1 || { echo >&2 "❌ Hata: docker compose yüklü değil. Kurulum iptal edildi."; exit 1; }

# 2. .env Dosyasının Oluşturulması
if [ ! -f .env ]; then
    echo "📄 .env.example kopyalanarak .env dosyası oluşturuluyor..."
    cp .env.example .env
else
    echo "✅ .env dosyası zaten mevcut."
fi

# 3. Master Encryption Key Üretimi
if grep -q "MASTER_ENCRYPTION_KEY=your-32-byte-base64-key-here" .env; then
    echo "🔐 Güvenli Master Encryption Key üretiliyor..."
    # 32 byte url-safe base64 key üret (Python kullanarak)
    NEW_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32 | tr -d '\n' | tr '/+' '_-')
    
    if [ "$OSTYPE" = "darwin"* ]; then
        sed -i '' "s/MASTER_ENCRYPTION_KEY=your-32-byte-base64-key-here/MASTER_ENCRYPTION_KEY=${NEW_KEY}/g" .env
    else
        sed -i "s/MASTER_ENCRYPTION_KEY=your-32-byte-base64-key-here/MASTER_ENCRYPTION_KEY=${NEW_KEY}/g" .env
    fi
    echo "✅ Başarı: .env dosyasına yeni key eklendi."
fi

# 4. Host Klasörlerinin ve İzinlerinin Ayarlanması (Docker bağlamaları için)
echo "📁 Gerekli klasörler oluşturuluyor..."
mkdir -p logs screenshots certs backups

# Docker container içindeki 'ghostuser' (UID 1000) bu klasörlere yazabilsin diye izin veriyoruz
# Linux sistemlerinde volume permission sorununu çözer
if [ "$OSTYPE" = "linux-gnu"* ]; then
    echo "🔧 Klasör izinleri ayarlanıyor (UID: 1000, GID: 1000)..."
    sudo chown -R 1000:1000 logs screenshots || echo "⚠️ İzinleri ayarlarken root yetkisi gerekebilir. İzin hatası alırsanız 'sudo chown -R 1000:1000 logs screenshots' çalıştırın."
fi

echo "---------------------------------------"
echo "🎉 Kurulumun ilk aşaması tamamlandı!"
echo ""
echo "👉 SONRAKİ ADIMLAR:"
echo "1. '.env' dosyasını açın (nano .env)"
echo "2. TELEGRAM_BOT_TOKEN ve ilgili LLM API (Google/OpenAI/Anthropic) anahtarını ekleyin."
echo "3. Sistemi başlatmak için şu komutu çalıştırın:"
echo "   docker compose up -d"
echo ""
echo "Veritabanı tabloları (migration'lar) otomatik olarak oluşturulacaktır."
echo "İyi dersler! 🎓"
