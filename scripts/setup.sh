#!/bin/bash
# GhostAttend — Automatic Setup Script
# Bu script, projeyi klonlayan kullanıcının kurulumunu "tek tık" seviyesine indirir.

set -e

echo "👻 GhostAttend Kurulumuna Hoş Geldiniz!"
echo "---------------------------------------"

# 1. Gerekli araçların kontrolü
command -v docker >/dev/null 2>&1 || { echo >&2 "❌ Hata: docker yüklü değil. Kurulum iptal edildi."; exit 1; }

COMPOSE_FILE="docker-compose.dev.yml"
if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose -f "$COMPOSE_FILE")
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose -f "$COMPOSE_FILE")
else
    echo >&2 "❌ Hata: docker compose yüklü değil. Kurulum iptal edildi."
    exit 1
fi

# 2. .env Dosyasının Oluşturulması
if [ ! -f .env ]; then
    echo "📄 .env.example kopyalanarak .env dosyası oluşturuluyor..."
    cp .env.example .env
else
    echo "✅ .env dosyası zaten mevcut."
fi

# 3. Etkileşimli .env Ayarları
echo ""
echo "⚙️  Bot ve API Ayarları"
echo "Bu aşamada botunuzun çalışması için gereken temel anahtarları gireceksiniz."
echo "Eğer önceden .env dosyanızı ayarladıysanız bu adımları Enter'a basarak geçebilirsiniz."
echo ""

read -p "Telegram Bot Token'ınızı giriniz: " tg_token
if [ ! -z "$tg_token" ]; then
    if [ "$OSTYPE" = "darwin"* ]; then
        sed -i '' "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${tg_token}|" .env
    else
        sed -i "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${tg_token}|" .env
    fi
fi

echo ""
echo "LLM Provider Seçimi (Agent'ın beyni)"
echo "1) Google (Gemini - Önerilen/Ücretsiz)"
echo "2) OpenAI (GPT)"
echo "3) Anthropic (Claude)"
read -p "Seçiminiz (1/2/3) [Varsayılan: 1]: " provider_choice

provider="google"
target_key_var="GOOGLE_API_KEY"
if [ "$provider_choice" = "2" ]; then
    provider="openai"
    target_key_var="OPENAI_API_KEY"
elif [ "$provider_choice" = "3" ]; then
    provider="anthropic"
    target_key_var="ANTHROPIC_API_KEY"
fi

if [ "$OSTYPE" = "darwin"* ]; then
    sed -i '' "s|^AGENT_LLM_PROVIDER=.*|AGENT_LLM_PROVIDER=${provider}|" .env
else
    sed -i "s|^AGENT_LLM_PROVIDER=.*|AGENT_LLM_PROVIDER=${provider}|" .env
fi

read -p "${provider} API Key'inizi giriniz: " api_key
if [ ! -z "$api_key" ]; then
    if [ "$OSTYPE" = "darwin"* ]; then
        sed -i '' "s|^${target_key_var}=.*|${target_key_var}=${api_key}|" .env
    else
        sed -i "s|^${target_key_var}=.*|${target_key_var}=${api_key}|" .env
    fi
fi

# 4. Şifrelerin ve Anahtarların Otomatik Üretimi
echo ""
echo "🔐 Güvenlik ve Veritabanı şifreleri otomatik denetleniyor..."

if grep -q "^MASTER_ENCRYPTION_KEY=[[:space:]]*#" .env || grep -q "^MASTER_ENCRYPTION_KEY=$" .env; then
    NEW_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
    if [ "$OSTYPE" = "darwin"* ]; then
        sed -i '' "s|^MASTER_ENCRYPTION_KEY=.*|MASTER_ENCRYPTION_KEY=${NEW_KEY}|" .env
    else
        sed -i "s|^MASTER_ENCRYPTION_KEY=.*|MASTER_ENCRYPTION_KEY=${NEW_KEY}|" .env
    fi
fi

if grep -q "^POSTGRES_USER=[[:space:]]*$" .env; then
    if [ "$OSTYPE" = "darwin"* ]; then sed -i '' "s|^POSTGRES_USER=.*|POSTGRES_USER=ghost_admin|" .env; else sed -i "s|^POSTGRES_USER=.*|POSTGRES_USER=ghost_admin|" .env; fi
fi
if grep -q "^POSTGRES_PASSWORD=[[:space:]]*$" .env; then
    PG_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))" 2>/dev/null || openssl rand -base64 16)
    if [ "$OSTYPE" = "darwin"* ]; then sed -i '' "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PG_PASS}|" .env; else sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PG_PASS}|" .env; fi
fi

if grep -q "^REDIS_PASSWORD=[[:space:]]*$" .env; then
    RD_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))" 2>/dev/null || openssl rand -base64 16)
    if [ "$OSTYPE" = "darwin"* ]; then sed -i '' "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${RD_PASS}|" .env; else sed -i "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${RD_PASS}|" .env; fi
fi

# 5. Host Klasörlerinin Ayarlanması
echo "📁 Host klasörleri ayarlanıyor..."
mkdir -p logs screenshots certs backups data

if [ "$OSTYPE" = "linux-gnu"* ]; then
    sudo chown -R 1000:1000 logs screenshots 2>/dev/null || echo "⚠️ Uyarı: log ve screenshot klasörlerine yazma izni verilemedi, root olmayabilirsiniz."
fi

echo "---------------------------------------"
echo "🎉 Kurulum başarıyla tamamlandı!"
echo ""
read -p "Sistemi şimdi başlatmak ister misiniz? (Y/n): " start_now
start_now=${start_now:-Y}

if [[ "$start_now" =~ ^[Yy]$ ]]; then
    echo "🚀 Docker Compose ile sistem başlatılıyor..."
    "${COMPOSE[@]}" up -d
    echo "Sistem başlatıldı! Logları görmek için: ${COMPOSE[*]} logs -f bot worker"
else
    echo "Kurulum tamamlandı. İstediğiniz zaman '${COMPOSE[*]} up -d' komutuyla başlatabilirsiniz."
fi
echo "İyi dersler! 🎓"
