# Kurulum Rehberi

Bu rehber sifirdan klonlayan bir kullanicinin repo hakkinda hicbir sey bilmeden sistemi ayağa kaldirabilmesi icin yazildi.

## 1. Gereksinimler

Asagidakiler makinede kurulu olmali:

- Docker
- Docker Compose v2
- Telegram bot token
- En az bir LLM API key

Windows icin Docker Desktop, Linux icin Docker Engine + Compose plugin yeterlidir.

## 2. En kolay kurulum

### Windows

```powershell
git clone https://github.com/xPoleStarx/ghost-attend.git
cd ghost-attend
.\scripts\setup.ps1
```

### Linux / macOS

```bash
git clone https://github.com/xPoleStarx/ghost-attend.git
cd ghost-attend
bash scripts/setup.sh
```

Kurulum scripti:

- `.env` olusturur
- gerekli sifreleri uretir
- `DATABASE_URL` ve `REDIS_URL` alanlarini senkronize eder
- development servislerini `--build` ile baslatir

## 3. Gunluk kullanim

Kurulumdan sonra ham `docker compose ...` yazmak zorunda degilsin.

### Windows

```powershell
.\scripts\dev.ps1 up
.\scripts\dev.ps1 rebuild
.\scripts\dev.ps1 logs
.\scripts\dev.ps1 ps
.\scripts\dev.ps1 migrate
.\scripts\dev.ps1 down
.\scripts\dev.ps1 reset
```

### Linux / macOS

```bash
./scripts/dev.sh up
./scripts/dev.sh rebuild
./scripts/dev.sh logs
./scripts/dev.sh ps
./scripts/dev.sh migrate
./scripts/dev.sh down
./scripts/dev.sh reset
```

## 4. Hangi komut ne zaman?

- `up`: servisleri kaldirir
- `rebuild`: image rebuild + bot/worker/scheduler recreate
- `logs`: bot, worker ve scheduler loglarini izler
- `ps`: servis durumunu gosterir
- `migrate`: alembic migration calistirir
- `down`: servisleri durdurur
- `reset`: servisleri ve volume'leri siler

## 5. Bu repodaki son degisiklikler icin ne gerekli?

Son yaptigimiz degisiklikler:

- Python kaynak kodu
- worker/scheduler environment
- compose dosyalari

Bu yuzden en dogru komut:

### Windows

```powershell
.\scripts\dev.ps1 rebuild
```

### Linux / macOS

```bash
./scripts/dev.sh rebuild
```

Sadece `up` degil, ozellikle `rebuild` onerilir.

## 6. Kurulum sonrasi ilk kontrol

1. `logs` komutunu calistir.
2. Telegram'da bota `/start` gonder.
3. DYS URL ve giris bilgilerini ekle.
4. `/upload_schedule` ile program yukle.
5. `/status` ile derslerin ve joblarin gorundugunu dogrula.

## 7. .env alanlari

Temel alanlar:

```env
ENVIRONMENT=development
TELEGRAM_BOT_TOKEN=
GOOGLE_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
AGENT_LLM_PROVIDER=google
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ghostattend
POSTGRES_USER=ghost_admin
POSTGRES_PASSWORD=...
DATABASE_URL=postgresql+asyncpg://...
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=...
REDIS_URL=redis://:...@redis:6379/0
MASTER_ENCRYPTION_KEY=...
BROWSER_HEADLESS=false
```

Notlar:

- Host `.env` dosyanda `BROWSER_HEADLESS=false` kalabilir.
- Worker/scheduler compose tarafinda headless olarak override edilir.
- Bot development ortaminda polling ile calisir.

## 8. SIk gorulen problemler

### Bot cevap vermiyor

- `.\scripts\dev.ps1 logs` veya `./scripts/dev.sh logs`
- `TELEGRAM_BOT_TOKEN` dogru mu kontrol et

### Worker browser acamiyor

- Yeni build aldigindan emin ol: `rebuild`
- Worker loglarinda `agent.browser_mode` kaydini kontrol et

### Migration gerekiyor

- `migrate` komutunu calistir

### Her seyi sifirlamak istiyorum

- `reset`
- sonra tekrar `up` veya `rebuild`

## 9. Production notu

Bu repo varsayilan olarak development akisi icin optimize edildi. Production'a gecmeden once:

- `docker-compose.yml` kullan
- webhook/domain/SSL ayarla
- `.env` icinde production degerlerini set et
- deployment adimlarini ayri test et
