# Kurulum Rehberi

## Gereksinimler

| Gereksinim | Minimum |
|---|---|
| VPS | 2 vCPU, 2GB RAM, 20GB disk |
| OS | Ubuntu 22.04+ / Debian 12+ |
| Docker | 24.0+ |
| Docker Compose | v2.20+ |

## Hızlı Kurulum

```bash
# 1. Repo'yu klonla
git clone https://github.com/your-username/ghost-attend.git
cd ghost-attend

# 2. Tek tık kurulum scriptini çalıştır
# (Bu script .env dosyanızı oluşturur, güvenli şifreleme anahtarını üretir ve izinleri ayarlar)
bash scripts/setup.sh

# 3. .env dosyasını düzenle
nano .env
# → Sadece TELEGRAM_BOT_TOKEN ve LLM API (Google/OpenAI) key'lerini girmeniz yeterlidir.

# 4. Sistemi başlat
docker compose up -d

# 5. Logları kontrol et
docker compose logs -f bot
```

> 💡 **Not:** Veritabanı tabloları sistem başlatıldığında otomatik olarak oluşturulur. Ekstra bir veritabanı komutu çalıştırmanıza gerek yoktur!

## .env Yapılandırması

### Zorunlu Alanlar

```env
# Telegram (@BotFather'dan al)
TELEGRAM_BOT_TOKEN=your-bot-token

# LLM (en az biri)
GOOGLE_API_KEY=your-key
# veya
OPENAI_API_KEY=your-key
# veya
ANTHROPIC_API_KEY=your-key

# Veritabanı
POSTGRES_USER=ghost
POSTGRES_PASSWORD=güçlü-şifre-buraya

# Güvenlik (setup.sh otomatik üretir)
MASTER_ENCRYPTION_KEY=auto-generated
```

### LLM Provider Seçimi

```env
# Önerilen (en ucuz + hızlı)
AGENT_LLM_PROVIDER=google
AGENT_LLM_MODEL=gemini-2.0-flash-lite

# Alternatif
AGENT_LLM_PROVIDER=openai
AGENT_LLM_MODEL=gpt-4o-mini

# Premium
AGENT_LLM_PROVIDER=anthropic
AGENT_LLM_MODEL=claude-3-5-haiku-latest
```

## Telegram Bot Oluşturma

1. Telegram'da [@BotFather](https://t.me/BotFather)'a git
2. `/newbot` yaz
3. Bot adı ve kullanıcı adı gir
4. Token'ı kopyala → `.env`'ye yapıştır

## Production Webhook Ayarı

```env
TELEGRAM_WEBHOOK_URL=https://yourdomain.com
TELEGRAM_WEBHOOK_SECRET=rastgele-secret-key
```

SSL sertifikası için Let's Encrypt kullanın:
```bash
sudo certbot certonly --standalone -d yourdomain.com
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./certs/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ./certs/
```

## Sorun Giderme

| Sorun | Çözüm |
|---|---|
| Bot yanıt vermiyor | `docker compose logs bot` kontrol et |
| DB bağlantı hatası | `docker compose ps postgres` — sağlık durumunu kontrol et |
| Playwright hata | `docker compose exec bot playwright install chromium` |
| Memory yetersiz | `docker-compose.yml`'de memory limit'i artır |
