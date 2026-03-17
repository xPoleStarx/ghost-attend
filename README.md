# 🤖 GhostAttend

> Üniversite canlı derslerine otonom katılım sağlayan Telegram bot + web agent.

[![CI](https://github.com/GhostAttend/ghost-attend/actions/workflows/ci.yml/badge.svg)](https://github.com/GhostAttend/ghost-attend/actions/workflows/ci.yml)

## 🎯 Ne Yapar?

**(Demo/Ekran Görüntüsü buraya eklenecek - Örnek: `![GhostAttend Demo](docs/assets/demo.gif)`)**

1. **Ders programını fotoğraftan okur** — Vision LLM (Gemini/GPT-4o/Claude) ile
2. **Dersten 5dk önce aktifleşir** — APScheduler + Celery ile zamanlar
3. **DYS'ye giriş yapar** — Kayıtlı credential'lar veya cookie ile
4. **Ders linkini bulur** — DYS'te Teams/Zoom linkini otonom keşfeder
5. **Derse katılır** — Kamera/mikrofon kapalı, sessizce
6. **MFA halledebilir** — SMS kodu Telegram'dan alır, Authenticator push destekler
7. **Her adımda screenshot gönderir** — Telegram üzerinden takip et
8. **12 senaryoya hazır** — Login fail, link bulunamadı, sayfa donması, ağ hatası...

### 🌐 Desteklenen Platformlar
- ✅ Microsoft Teams
- ✅ Zoom
- ⏳ Google Meet (Yakında)
- ⏳ WebEx (Yakında)

## 📱 Telegram Komutları

| Komut | Açıklama |
|---|---|
| `/start` | İlk kurulum |
| `/upload_schedule` | Ders programı yükle (fotoğraf) |
| `/status` | Zamanlanmış dersleri gör |
| `/courses` | Kayıtlı derslerini listele |
| `/pause` / `/resume` | Otomasyonu durdur/devam ettir |
| `/cancel` | Aktif oturumu iptal et |
| `/reauth` | Giriş bilgilerini güncelle |
| `/help` | Tüm komutlar |

## 🏗️ Mimari

```
Telegram Bot ←→ Redis ←→ Celery Worker ←→ browser-use + Playwright
     ↕              ↕              ↕
  PostgreSQL    APScheduler    Vision LLM
```

## 🚀 Hızlı Başlangıç

**Ön Koşullar:** Sisteminizde [Docker](https://docs.docker.com/get-docker/) ve [Docker Compose](https://docs.docker.com/compose/) kurulu olmalıdır. Ayrıca bir [Telegram Bot Token](https://core.telegram.org/bots#how-do-i-create-a-bot) ve en az bir LLM Provider API Key (Google Gemini, OpenAI veya Anthropic) gereklidir.

```bash
git clone https://github.com/your-username/ghost-attend.git
cd ghost-attend
./scripts/setup.sh
# .env düzenle → TELEGRAM_BOT_TOKEN ve API key'leri gir
docker compose up -d
```

📖 Detaylı kurulum: [docs/SETUP.md](docs/SETUP.md)

## 🛡️ Güvenlik

- Şifreler **Fernet + PBKDF2-SHA256** ile şifrelenir (user-specific key)
- Telegram'daki şifre mesajları **anında silinir**
- Docker container'lar **non-root** çalışır
- 📖 [docs/SECURITY.md](docs/SECURITY.md)

## 📚 Dokümantasyon

- [Kurulum Rehberi](docs/SETUP.md)
- [Katkıda Bulunma](docs/CONTRIBUTING.md)
- [Güvenlik Politikası](docs/SECURITY.md)
- [Senaryo Matrisi](docs/SCENARIOS.md)
- [Mimari Dokümanı](architecture.md)

## ⚖️ Lisans

MIT — [LICENSE](LICENSE)

## 💬 Destek ve İletişim

Herhangi bir sorun yaşarsanız, üniversitenizin portalı desteklenmiyorsa veya yeni bir özellik önermek isterseniz lütfen [Issues](https://github.com/your-username/ghost-attend/issues) sekmesinden bildirimde bulunun.

> ⚠️ **Sorumluluk:** Bu yazılım eğitim amaçlıdır. Üniversite yönetmeliklerine
> ve kullanılan platform ToS'larına uygunluk kullanıcının sorumluluğundadır.
