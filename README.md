# GhostAttend

Telegram bot + web agent tabanli, universite canli derslerine otonom katilim sistemi.

## Ne yapar?

- Ders programini goruntuden veya metinden parse eder.
- Dersleri scheduler ile zamanlar.
- Worker tarafinda DYS/OBS uzerinden Teams/Zoom linkini bulup derse katilir.
- Telegram uzerinden durum, ekran goruntusu ve hata bildirimi gonderir.

## Hizli baslangic

Bu repo icin en kolay yol kurulum scriptini bir kez, sonra da gunluk isler icin `dev` scriptini kullanmaktir.

### Windows

```powershell
git clone https://github.com/xPoleStarx/ghost-attend.git
cd ghost-attend
.\scripts\setup.ps1
```

Kurulumdan sonra gunluk kullanim:

```powershell
.\scripts\dev.ps1 up
.\scripts\dev.ps1 logs
.\scripts\dev.ps1 rebuild
```

### Linux / macOS

```bash
git clone https://github.com/xPoleStarx/ghost-attend.git
cd ghost-attend
bash scripts/setup.sh
```

Kurulumdan sonra gunluk kullanim:

```bash
./scripts/dev.sh up
./scripts/dev.sh logs
./scripts/dev.sh rebuild
```

## Bu degisikliklerin gecerli olmasi icin ne yapmaliyim?

Hangi compose dosyasini kullandigina gore degisiyor:

- `docker-compose.dev.yml` kullaniyorsan:
  - `src/` altindaki Python degisiklikleri volume ile mount edildigi icin cogu zaman sadece container restart yeterlidir.
  - Ama bu tur degisikliklerde `docker-compose.dev.yml` environment'i de degistigi icin en temiz yol `rebuild` calistirmaktir.
- `docker-compose.yml` kullaniyorsan:
  - Image icine kopyalandigi icin rebuild gerekir.

Onerilen komut:

```powershell
.\scripts\dev.ps1 rebuild
```

veya

```bash
./scripts/dev.sh rebuild
```

## En sik kullanilan komutlar

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

## Kurulum ozeti

`setup` scriptleri sunlari yapar:

- `.env.example` dosyasini `.env` olarak kopyalar.
- Telegram token ve tek bir LLM provider API key ister.
- `MASTER_ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD` gibi alanlari uretir.
- `DATABASE_URL` ve `REDIS_URL` degerlerini gercek sifrelerle senkronize eder.
- Development ortaminda `docker compose up -d --build` ile sistemi kaldirir.

## Servisler

- `bot`: Telegram botu
- `worker`: Celery worker + Playwright/browser-use
- `scheduler`: APScheduler tetikleyicisi
- `postgres`: kalici veri
- `redis`: queue, state, scheduler store

## Dikkat edilmesi gerekenler

- Worker/scheduler container icinde browser her zaman headless calisir. Bu bilincli bir ayardir.
- `docker-compose.dev.yml` development icindir.
- Production icin `docker-compose.yml` ve uygun domain/SSL/webhook ayarlari gerekir.

## Dokumantasyon

- [Kurulum Rehberi](docs/SETUP.md)
- [Trigger Smoke Test](docs/TRIGGER_TEST.md)
- [Guvenlik](docs/SECURITY.md)
- [Katki Rehberi](docs/CONTRIBUTING.md)
- [Mimari](architecture.md)

## Lisans

MIT
