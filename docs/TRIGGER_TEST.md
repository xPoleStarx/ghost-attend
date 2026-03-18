# Tetikleme (T-5dk) Smoke Test Checklist (Dev/Prod)

Bu doküman, **yakın zamana ayarlı bir ders** ile uçtan uca akışı doğrulamak için hazırlanmıştır:

- Bot: dersi zamanlar (APScheduler jobstore → Redis **db=1**)
- Scheduler: job’u restore eder ve tetikler
- Worker: Celery task’ını alır, oturumu başlatır
- Telegram: reminder + screenshot/checkpoint mesajlarını görürsün

## 0) Ön Koşullar

- Telegram botun çalışıyor (komutlara cevap veriyor)
- `.env` dosyan doğru (Telegram token, provider key, DB/Redis ayarları)
- İlgili stack **tek bir compose projesi** altında koşuyor (dev ve prod aynı anda aynı isimle koşmuyor)

## 1) Stack’i temiz ve deterministik başlat

### Dev (hot-reload)

```powershell
$env:COMPOSE_PROJECT_NAME="ghostattend_dev"
docker compose -f docker-compose.dev.yml down
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml ps
```

### Prod-benzeri (image)

```powershell
$env:COMPOSE_PROJECT_NAME="ghostattend"
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml up -d --build
docker compose -f docker-compose.yml ps
```

Beklenen servisler: `bot`, `scheduler`, `worker`, `postgres`, `redis` (opsiyonel `nginx`).

## 2) Sağlık kontrolü (scheduler heartbeat)

Telegram’da:

- `/health` komutunu gönder
- Beklenen: `scheduler_heartbeat: evet` benzeri bir çıktı

Sorun varsa hızlı bakış:

```powershell
docker compose -f docker-compose.dev.yml logs --tail 200 scheduler bot
```

> Prod için `docker-compose.yml` ile aynı komutu çalıştır.

## 3) Jobstore doğrulaması (Redis db=1)

Telegram’da:

- `/status` komutunu gönder
- Beklenen:
  - Scheduler job sayısı **0’dan büyük** (en azından “kayıtlı ders” varken)
  - `bot.status_job_list_failed` benzeri hata yok

Redis’te kaba doğrulama:

### Dev (redis şifresiz)

```powershell
docker compose -f docker-compose.dev.yml exec redis redis-cli -n 1 DBSIZE
docker compose -f docker-compose.dev.yml exec redis redis-cli -n 1 KEYS "*apscheduler*"
```

### Prod (redis şifreli)

```powershell
docker compose -f docker-compose.yml exec redis redis-cli -a $env:REDIS_PASSWORD -n 1 DBSIZE
docker compose -f docker-compose.yml exec redis redis-cli -a $env:REDIS_PASSWORD -n 1 KEYS "*apscheduler*"
```

Notlar:

- `DBSIZE` **0** ise scheduler jobstore’a yazmıyor ya da “ders/job” yok.
- `KEYS` çıktısı ortama göre değişebilir; amaç db=1’in boş olmadığını görmek.

## 4) T-5dk tetikleme senaryosu (esas smoke test)

Amaç: **Şu andan 5–7 dakika sonraya** bir ders ayarlayıp tetiklemeyi gözlemek.

### 4.1 Test verisini hazırla

Aşağıdaki iki yoldan birini seç:

- **Yol A (önerilen)**: Telegram’da `/upload_schedule` ile **tek derslik**, saati 5–7 dk sonra olan bir program yükle.
- **Yol B**: Mevcut bir dersi (varsa) “yakın zamana” çekecek şekilde güncelle (projedeki agent akışı bunu destekliyorsa).

### 4.2 Beklenen akış (zaman çizelgesi)

- **T-5 dk civarı**: Telegram’da reminder/hatırlatma mesajı
- **T-0 civarı**: Worker tarafında `attend`/`join` benzeri task başlangıcı
- **T+0..T+2 dk**: Telegram’da screenshot/checkpoint mesajları (login → ders linki → join)

### 4.3 Loglardan doğrulama (en güvenilir sinyal)

Dev:

```powershell
docker compose -f docker-compose.dev.yml logs -f --tail 200 bot scheduler worker
```

Prod:

```powershell
docker compose -f docker-compose.yml logs -f --tail 200 bot scheduler worker
```

Beklenen göstergeler:

- **Scheduler**: job restore / job run / next run hesaplama (hata yok)
- **Worker**: Celery task receive + task start (attend/join akışı)
- **Bot**: reminder gönderimi + durum mesajları

## 5) Başarısızlık durumunda hızlı teşhis

- `/status` job sayısı 0:
  - Scheduler’ın Redis’e bağlandığını doğrula (REDIS_URL host/port)
  - Redis db=1 boş mu kontrol et (`DBSIZE`)
- T-5 mesajı gelmiyor ama job var:
  - Scheduler logunda “misfire”/timezone hatası var mı bak
  - Container saatini kontrol et:

```powershell
docker compose -f docker-compose.dev.yml exec scheduler python -c "import datetime; print(datetime.datetime.now())"
```

- Worker task almıyor:
  - Worker logunda broker bağlantı hatası var mı bak
  - `REDIS_URL` hem bot hem worker için aynı mı doğrula

