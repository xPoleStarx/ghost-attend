# Tetikleme (T-5dk) Smoke Test Checklist (Dev/Prod)

Bu dokuman, yakin zamana ayarli bir ders ile uctan uca akis dogrulamak icin hazirlandi:

- Bot: dersi zamanlar (APScheduler jobstore -> Redis `db=1`)
- Scheduler: job'u restore eder ve tetikler
- Worker: Celery task'ini alir, oturumu baslatir
- Telegram: reminder + screenshot/checkpoint mesajlarini gorursun

## 0) On Kosullar

- Telegram botun calisiyor (komutlara cevap veriyor)
- `.env` dosyan dogru (Telegram token, provider key, DB/Redis ayarlari)
- Ilgili stack tek bir compose projesi altinda kosuyor (dev ve prod ayni anda ayni isimle kosmuyor)
- Kullanicinin timezone bilgisi dogru ayarli:

```text
/timezone Europe/Istanbul
```

## 1) Stack'i temiz ve deterministik baslat

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

## 2) Saglik kontrolu (scheduler heartbeat)

Telegram'da:

- `/health` komutunu gonder
- Beklenen: `scheduler_heartbeat: evet` benzeri bir cikti

Sorun varsa hizli bakis:

```powershell
docker compose -f docker-compose.dev.yml logs --tail 200 scheduler bot
```

Prod icin `docker-compose.yml` ile ayni komutu calistir.

## 3) Jobstore dogrulamasi (Redis db=1)

Telegram'da:

- `/status` komutunu gonder
- Beklenen:
  - Scheduler job sayisi 0'dan buyuk
  - `bot.status_job_list_failed` benzeri hata yok
  - `next_run` kullanicinin kendi timezone'una gore anlamli gorunuyor

Redis'te kaba dogrulama:

### Dev (redis sifresiz)

```powershell
docker compose -f docker-compose.dev.yml exec redis redis-cli -n 1 DBSIZE
docker compose -f docker-compose.dev.yml exec redis redis-cli -n 1 KEYS "*apscheduler*"
```

### Prod (redis sifreli)

```powershell
docker compose -f docker-compose.yml exec redis redis-cli -a $env:REDIS_PASSWORD -n 1 DBSIZE
docker compose -f docker-compose.yml exec redis redis-cli -a $env:REDIS_PASSWORD -n 1 KEYS "*apscheduler*"
```

Notlar:

- `DBSIZE` 0 ise scheduler jobstore'a yazmiyor ya da ders/job yok.
- `KEYS` ciktisi ortama gore degisebilir; amac db=1'in bos olmadigini gormek.

## 4) T-5dk tetikleme senaryosu (esas smoke test)

Amac: Su andan 5-7 dakika sonraya bir ders ayarlayip tetiklemeyi gozlemek.

### 4.1 Test verisini hazirla

Asagidaki iki yoldan birini sec:

- Yol A (onerilen): Telegram'da `/upload_schedule` ile tek derslik, saati 5-7 dk sonra olan bir program yukle.
- Yol B: Mevcut bir dersi yakin zamana cekecek sekilde guncelle.

### 4.2 Beklenen akis (zaman cizelgesi)

- T-5 dakika tam olarak: Telegram'da "son 5 dakika, giris yapiyorum" mesaji
- T-5..T-3 dakika: Login / DYS / MFA benzeri ilk ilerleme mesajlari ve ekran goruntuleri
- T-3..T-0 dakika: Ders linki bulundu / join asamasina gecildi mesajlari ve ekran goruntuleri
- T-0 civari: Worker tarafinda `attend` / `join` task baslangici
- T+0..T+2 dakika: Telegram'da screenshot/checkpoint mesajlari (login -> ders linki -> join -> connected)

### 4.3 Loglardan dogrulama (en guvenilir sinyal)

Dev:

```powershell
docker compose -f docker-compose.dev.yml logs -f --tail 200 bot scheduler worker
```

Prod:

```powershell
docker compose -f docker-compose.yml logs -f --tail 200 bot scheduler worker
```

Beklenen gostergeler:

- Scheduler: job restore / job run / next run hesaplama (hata yok)
- Worker: Celery task receive + task start (attend/join akisi)
- Bot: reminder gonderimi + durum mesajlari + screenshot bildirimleri

## 5) Basarisizlik durumunda hizli teshis

- `/status` job sayisi 0:
  - Scheduler'in Redis'e baglandigini dogrula (`REDIS_URL` host/port)
  - Redis db=1 bos mu kontrol et (`DBSIZE`)
- T-5 mesaji gelmiyor ama job var:
  - Scheduler logunda timezone veya misfire hatasi var mi bak
  - Kullanici timezone degeri dogru mu kontrol et: `/timezone`
  - Container saatini kontrol et:

```powershell
docker compose -f docker-compose.dev.yml exec scheduler python -c "import datetime; print(datetime.datetime.now())"
```

- Worker task almiyor:
  - Worker logunda broker baglanti hatasi var mi bak
  - `REDIS_URL` hem bot hem worker icin ayni mi dogrula
