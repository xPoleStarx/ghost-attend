# 🎓 GhostAttend — Project Constitution

> **Agentic IDE Context Document**
> Bu doküman Antigravity, Cursor, Claude Code veya benzeri agentic IDE'ler için birincil context kaynağıdır.
> Projeye dair tüm kararlar, mimari seçimler ve implementasyon detayları burada yaşar.
> Herhangi bir ambiguity durumunda bu doküman referans alınır.

---

## 📋 İçindekiler

1. [Proje Vizyonu](#1-proje-vizyonu)
2. [Sistem Mimarisi](#2-sistem-mimarisi)
3. [Klasör Yapısı](#3-klasör-yapısı)
4. [Tech Stack & Bağımlılıklar](#4-tech-stack--bağımlılıklar)
5. [Veritabanı Şeması](#5-veritabanı-şeması)
6. [Telegram Bot — Kullanıcı Akışları](#6-telegram-bot--kullanıcı-akışları)
7. [Credential Toplama & Güvenlik](#7-credential-toplama--güvenlik)
8. [Vision LLM — Ders Programı Parsing](#8-vision-llm--ders-programı-parsing)
9. [Web Agent Core](#9-web-agent-core)
10. [Senaryo Matrisi](#10-senaryo-matrisi)
11. [Scheduler Sistemi](#11-scheduler-sistemi)
12. [Bildirim Servisi](#12-bildirim-servisi)
13. [Docker & Deployment](#13-docker--deployment)
14. [CI/CD Pipeline](#14-cicd-pipeline)
15. [Test Stratejisi (TDD)](#15-test-stratejisi-tdd)
16. [Environment & Config](#16-environment--config)
17. [Hata Yönetimi & Logging](#17-hata-yönetimi--logging)
18. [Açık Kaynak Standartları](#18-açık-kaynak-standartları)
19. [Yol Haritası (MVP → v1.0)](#19-yol-haritası-mvp--v10)

---

## 1. Proje Vizyonu

### Ne Yapar?

GhostAttend, üniversite öğrencilerinin Teams/Zoom tabanlı online derslerine **otonom bir web agent** aracılığıyla katılan, Telegram üzerinden yönetilen açık kaynaklı bir sistemdir.

### Temel Prensipler

| Prensip | Açıklama |
|---|---|
| **Self-hosted** | Her kullanıcı kendi VPS'ine kurar. Merkezi credential deposu yoktur. |
| **Agent-first** | Hardcode selector yok. LLM ekranı okur, karar verir. |
| **Screenshot transparency** | Her kritik adımda kullanıcı ekran görüntüsü alır. |
| **Graceful degradation** | Agent başarısız olduğunda kullanıcıyı sessizce bırakmaz, bildirir. |
| **Zero trust** | Credentials hiçbir zaman plaintext saklanmaz. |

### Kapsam Dışı (v1.0)

- Zoom, Google Meet dışı platformlar (ileride eklenir)
- Mobil uygulama (Telegram bot yeterli)
- Çoklu DYS desteği aynı anda (bir kullanıcı, bir üniversite)
- Ders notu alma, ödev takibi

---

## 2. Sistem Mimarisi

```
┌─────────────────────────────────────────────────────────────┐
│                    KULLANICI KATMANI                        │
│                  Telegram Bot Interface                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ python-telegram-bot webhooks
┌──────────────────────────▼──────────────────────────────────┐
│                   ORCHESTRATOR KATMANI                      │
│              FastAPI  ·  Bot Handler  ·  State Machine      │
└────────┬──────────────┬──────────────────────┬──────────────┘
         │              │                      │
┌────────▼───┐  ┌───────▼───────┐   ┌──────────▼──────────┐
│  VISION    │  │  SCHEDULER    │   │  SESSION MANAGER    │
│  SERVICE   │  │  APScheduler  │   │  Redis State Store  │
│  (Claude/  │  │  + Celery     │   │  + Cookie Vault     │
│   GPT-4o)  │  └───────┬───────┘   └──────────┬──────────┘
└────────────┘          │                      │
                ┌───────▼──────────────────────▼──────────┐
                │            WEB AGENT CORE               │
                │     browser-use  +  Playwright          │
                │     LLM Brain: Claude claude-opus-4-6 / GPT-4o   │
                └───────────────────┬─────────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │        HEDEF SİSTEMLER          │
                    │  DYS/OBS  →  Teams Web         │
                    │  (Üniversiteye göre değişir)    │
                    └────────────────────────────────┘
                                    │
                ┌───────────────────▼─────────────────────┐
                │          NOTIFICATION SERVICE           │
                │    Screenshot  →  Telegram API          │
                └─────────────────────────────────────────┘
```

### Servisler Arası İletişim

```
Bot Handler      →  FastAPI REST (internal)
FastAPI          →  Redis (session state, job queue)
FastAPI          →  PostgreSQL (kalıcı veri)
Scheduler        →  Celery Worker (async job dispatch)
Celery Worker    →  Web Agent (subprocess / async)
Web Agent        →  Notification Service (event emit)
Notification     →  Telegram Bot API
```

---

## 3. Klasör Yapısı

```
ghost-attend/
│
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                  # Test + lint pipeline
│   │   ├── cd.yml                  # Deploy to VPS
│   │   └── security-scan.yml       # Dependency vulnerability scan
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
│
├── src/
│   ├── bot/                        # Telegram Bot katmanı
│   │   ├── __init__.py
│   │   ├── main.py                 # Bot entry point
│   │   ├── handlers/
│   │   │   ├── __init__.py
│   │   │   ├── start.py            # /start, onboarding
│   │   │   ├── credentials.py      # Credential toplama conversation
│   │   │   ├── schedule.py         # Ders programı upload & onay
│   │   │   ├── session.py          # /status, /cancel, /sessions
│   │   │   └── admin.py            # /admin (self-host owner)
│   │   ├── keyboards/
│   │   │   ├── inline.py           # InlineKeyboardMarkup factory
│   │   │   └── reply.py            # ReplyKeyboardMarkup factory
│   │   ├── states.py               # ConversationHandler states (FSM)
│   │   └── middlewares.py          # Auth, rate limit middleware
│   │
│   ├── agent/                      # Web Agent Core
│   │   ├── __init__.py
│   │   ├── runner.py               # Agent lifecycle yönetimi
│   │   ├── task_builder.py         # Dinamik task string üretimi
│   │   ├── checkpoints.py          # Screenshot checkpoint tanımları
│   │   ├── mfa_handler.py          # MFA/2FA interrupt logic
│   │   └── strategies/
│   │       ├── __init__.py
│   │       ├── base.py             # Abstract DYS strategy
│   │       ├── generic.py          # Bilinmeyen DYS (full agent)
│   │       ├── obs_karadeniz.py    # Örnek: spesifik DYS adaptörü
│   │       └── ubys_ege.py         # Örnek: spesifik DYS adaptörü
│   │
│   ├── vision/                     # Vision LLM servisleri
│   │   ├── __init__.py
│   │   ├── schedule_parser.py      # Ders programı görseli → JSON
│   │   ├── screen_analyzer.py      # Runtime ekran analizi (agent için)
│   │   └── prompts.py              # Tüm LLM prompt'ları burada yaşar
│   │
│   ├── scheduler/                  # Zamanlama servisi
│   │   ├── __init__.py
│   │   ├── job_manager.py          # APScheduler job CRUD
│   │   ├── celery_app.py           # Celery konfigürasyonu
│   │   └── tasks.py                # Celery task tanımları
│   │
│   ├── core/                       # Business logic, domain
│   │   ├── __init__.py
│   │   ├── models.py               # Pydantic domain modelleri
│   │   ├── exceptions.py           # Custom exception hiyerarşisi
│   │   └── constants.py            # Sabitler (timeout, retry vs.)
│   │
│   ├── db/                         # Veritabanı katmanı
│   │   ├── __init__.py
│   │   ├── connection.py           # SQLAlchemy async engine
│   │   ├── models.py               # ORM modelleri
│   │   └── repositories/
│   │       ├── user.py
│   │       ├── course.py
│   │       └── session.py
│   │
│   ├── alembic/                    # Alembic migration dosyaları
│   │   ├── env.py
│   │   └── versions/
│   │
│   ├── security/                   # Güvenlik katmanı
│   │   ├── __init__.py
│   │   ├── encryption.py           # Fernet credential şifreleme
│   │   ├── vault.py                # Credential CRUD
│   │   └── session_store.py        # Cookie persistence
│   │
│   ├── notifications/              # Bildirim servisi
│   │   ├── __init__.py
│   │   ├── telegram_notifier.py    # Telegram mesaj/foto gönderimi
│   │   └── templates.py            # Mesaj template'leri
│   │
│   └── api/                        # Internal FastAPI (opsiyonel)
│       ├── __init__.py
│       ├── main.py
│       └── routes/
│           ├── health.py
│           └── webhooks.py
│
├── tests/
│   ├── unit/
│   │   ├── test_schedule_parser.py
│   │   ├── test_task_builder.py
│   │   ├── test_encryption.py
│   │   ├── test_job_manager.py
│   │   └── test_models.py
│   ├── integration/
│   │   ├── test_bot_flows.py       # Telegram conversation akışları
│   │   ├── test_agent_runner.py    # Mock browser ile agent testi
│   │   └── test_db_repositories.py
│   ├── e2e/
│   │   ├── test_full_flow.py       # Sandbox DYS üzerinde uçtan uca
│   │   └── fixtures/
│   │       ├── sample_schedule.jpg
│   │       └── mock_dys_server/    # Lokal fake DYS sunucusu
│   └── conftest.py                 # Pytest fixtures
│
├── docker/
│   ├── Dockerfile.bot
│   ├── Dockerfile.worker
│   ├── Dockerfile.agent
│   └── nginx.conf
│
├── scripts/
│   ├── setup.sh                    # İlk kurulum scripti
│   ├── backup_db.sh
│   └── rotate_keys.sh              # Encryption key rotasyonu
│
├── docs/
│   ├── SETUP.md                    # Kullanıcıya kurulum rehberi
│   ├── CONTRIBUTING.md
│   ├── SECURITY.md
│   ├── SCENARIOS.md                # Senaryo matrisi dokümantasyonu
│   └── diagrams/                   # Mimari diyagramlar
│
├── docker-compose.yml              # Production
├── docker-compose.dev.yml          # Development
├── docker-compose.test.yml         # Test ortamı
├── pyproject.toml                  # Poetry + araç konfigürasyonları
├── .env.example                    # Örnek env (asla .env commit edilmez)
├── .gitignore
├── Makefile                        # Kısa komutlar
├── README.md
└── GHOST_ATTEND_CONSTITUTION.md    # Bu dosya
```

---

## 4. Tech Stack & Bağımlılıklar

### Core Bağımlılıklar (`pyproject.toml`)

```toml
[tool.poetry.dependencies]
python = "^3.11"

# Bot
python-telegram-bot = {version = "^21.0", extras = ["job-queue"]}

# Web Agent
browser-use = "^0.1.40"
playwright = "^1.44.0"

# LLM
anthropic = "^0.28.0"
openai = "^1.35.0"           # Fallback LLM
google-generativeai = "^0.7.0"
langchain-google-genai = "^1.0.0"

# API & Async
fastapi = "^0.111.0"
uvicorn = {version = "^0.30.0", extras = ["standard"]}
httpx = "^0.27.0"

# Database
sqlalchemy = {version = "^2.0.0", extras = ["asyncio"]}
asyncpg = "^0.29.0"          # PostgreSQL async driver
alembic = "^1.13.0"
redis = {version = "^5.0.0", extras = ["hiredis"]}

# Task Queue
celery = {version = "^5.4.0", extras = ["redis"]}
apscheduler = "^3.10.0"

# Security
cryptography = "^42.0.0"    # Fernet encryption

# Validation
pydantic = "^2.7.0"
pydantic-settings = "^2.3.0"

# Utilities
pillow = "^10.3.0"           # Screenshot işlemleri
python-dateutil = "^2.9.0"
pytz = "^2024.1"
structlog = "^24.2.0"        # Structured logging

[tool.poetry.dev-dependencies]
pytest = "^8.2.0"
pytest-asyncio = "^0.23.0"
pytest-mock = "^3.14.0"
pytest-cov = "^5.0.0"
httpx = "^0.27.0"            # TestClient için
factory-boy = "^3.3.0"      # Test fixture factory
respx = "^0.21.0"            # HTTP mock
ruff = "^0.4.0"              # Linter + formatter
mypy = "^1.10.0"             # Type checker
pre-commit = "^3.7.0"
```

### LLM Model Seçimi

| Görev | Model | Neden |
|---|---|---|
| Ders programı parsing | `gemini-3.1-flash-lite` | En hızlı vision + JSON accuracy (En ucuz) |
| Agent brain (runtime) | `gemini-3.1-flash-lite` | Düşük gecikme, otonom görevler için ideal |
| GPT Alternatifi | `gpt-4o-mini` | Uygun fiyatlı vision + güçlü zeka |
| Anthropic Alternatifi | `claude-3-5-haiku` | Hızlı ve yetenekli (Vision destekli v3.5) |

**Model konfigürasyonu `src/core/constants.py`'da yaşar, hardcode edilmez.**

---

## 5. Veritabanı Şeması

```sql
-- Kullanıcılar
CREATE TABLE users (
    id              BIGINT PRIMARY KEY,          -- Telegram user_id
    username        VARCHAR(64),                 -- Telegram @username
    first_name      VARCHAR(128) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE,
    onboarding_step VARCHAR(32) DEFAULT 'start', -- FSM state
    timezone        VARCHAR(64) DEFAULT 'Europe/Istanbul'
);

-- Şifreli credential deposu
CREATE TABLE credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    type            VARCHAR(16) NOT NULL,  -- 'dys' | 'teams' | 'unified'
    dys_url         TEXT,                  -- https://obs.universite.edu.tr
    email_enc       BYTEA NOT NULL,        -- Fernet encrypted
    password_enc    BYTEA NOT NULL,        -- Fernet encrypted
    cookie_enc      BYTEA,                 -- Encrypted session cookies (JSON)
    cookie_expires_at TIMESTAMPTZ,
    last_verified   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, type)
);

-- Dersler
CREATE TABLE courses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         BIGINT REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(256) NOT NULL,
    instructor      VARCHAR(256),
    platform        VARCHAR(32) DEFAULT 'teams',  -- 'teams' | 'zoom' | 'meet' | 'unknown'
    day_of_week     SMALLINT NOT NULL,  -- 0=Pazartesi, 6=Pazar
    start_time      TIME NOT NULL,
    end_time        TIME NOT NULL,
    direct_url      TEXT,              -- Eğer kullanıcı direkt link verdiyse
    dys_search_hint TEXT,              -- DYS'de arama ipucu
    is_active       BOOLEAN DEFAULT TRUE,
    semester        VARCHAR(32),       -- '2024-2025-bahar'
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Agent oturumları (her ders girişi)
CREATE TABLE agent_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         BIGINT REFERENCES users(id),
    course_id       UUID REFERENCES courses(id),
    status          VARCHAR(32) NOT NULL DEFAULT 'pending',
    -- pending | running | joined | failed | cancelled | completed
    started_at      TIMESTAMPTZ,
    joined_at       TIMESTAMPTZ,       -- Derse gerçekten girilen an
    ended_at        TIMESTAMPTZ,
    failure_reason  TEXT,
    retry_count     SMALLINT DEFAULT 0,
    metadata        JSONB DEFAULT '{}', -- agent logs, step history
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Checkpoint (screenshot) kayıtları
CREATE TABLE session_checkpoints (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES agent_sessions(id) ON DELETE CASCADE,
    checkpoint_name VARCHAR(64) NOT NULL,
    screenshot_path TEXT,              -- VPS dosya yolu veya S3 URL
    telegram_file_id TEXT,             -- Telegram'a yüklendikten sonra cache
    occurred_at     TIMESTAMPTZ DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);

-- Bildirim logu
CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         BIGINT REFERENCES users(id),
    session_id      UUID REFERENCES agent_sessions(id),
    type            VARCHAR(32),   -- 'screenshot' | 'error' | 'mfa_request' | 'completed'
    message         TEXT,
    sent_at         TIMESTAMPTZ DEFAULT NOW(),
    is_read         BOOLEAN DEFAULT FALSE
);

-- İndeksler
CREATE INDEX idx_courses_user_active ON courses(user_id, is_active);
CREATE INDEX idx_sessions_user_status ON agent_sessions(user_id, status);
CREATE INDEX idx_sessions_created ON agent_sessions(created_at DESC);
```

---

## 6. Telegram Bot — Kullanıcı Akışları

### 6.1 FSM State Tanımları (`src/bot/states.py`)

```python
from enum import IntEnum

class OnboardingState(IntEnum):
    # Onboarding zinciri
    WELCOME              = 1
    ASK_DYS_URL          = 2
    ASK_CREDENTIAL_TYPE  = 3   # unified mi, ayrı mı
    ASK_DYS_EMAIL        = 4
    ASK_DYS_PASSWORD     = 5
    ASK_TEAMS_EMAIL      = 6
    ASK_TEAMS_PASSWORD   = 7
    VERIFY_CREDENTIALS   = 8
    ASK_SCHEDULE_PHOTO   = 9
    CONFIRM_COURSES      = 10
    SETUP_COMPLETE       = 11

class SessionState(IntEnum):
    # Aktif oturum yönetimi
    IDLE                 = 20
    MFA_WAITING          = 21   # Kullanıcıdan MFA kodu bekleniyor
    RUNNING              = 22
    CANCELLING           = 23
```

### 6.2 /start — Onboarding Akışı

```
Kullanıcı: /start
Bot: 
  👋 Hoş geldin! Ben GhostAttend.
  Üniversitedeki online derslerine senin adına katılacağım.
  
  Başlamak için birkaç bilgiye ihtiyacım var.
  Tüm bilgilerin şifreli saklanır ve sadece senin VPS'inde durur.
  
  [Kuruluma Başla 🚀]  [Nasıl Çalışır? ℹ️]

Kullanıcı: [Kuruluma Başla]
Bot:
  Önce üniversitenin öğrenci bilgi sistemi (OBS/DYS) adresini gir.
  Örnek: https://obs.ege.edu.tr
  
  (Bilmiyorsan üniversitenin web sitesine bak)

Kullanıcı: https://obs.ege.edu.tr
Bot:
  ✅ Adres kaydedildi.
  
  Microsoft hesabın (Teams için) ile DYS giriş bilgilerin
  aynı mı, yoksa farklı mı?
  
  [Aynı hesap ✓]  [Farklı hesaplar ✗]

── SENARYO A: Aynı hesap ──
Kullanıcı: [Aynı hesap]
Bot:
  📧 E-posta adresini yaz:
  (örn: 123456789@stu.ege.edu.tr)

Kullanıcı: 123456789@stu.ege.edu.tr
Bot:
  🔒 Şifreni yaz:
  ⚠️ Bu mesaj 30 saniye sonra otomatik silinecek.

Kullanıcı: P@ssw0rd123
Bot: [Kullanıcının mesajını ve kendi "şifreni yaz" mesajını siler]
     ✅ Bilgiler şifreli olarak kaydedildi.
     
     Şimdi DYS'ye giriş deniyorum... ⏳

── Arka planda: Playwright ile DYS login denemesi ──

Bot (başarı):
  ✅ DYS girişi başarılı!
     
  Şimdi ders programını yükle. Resim net ve okunaklar olsun.
  [Fotoğraf gönder 📷]

Bot (başarısız):
  ❌ Giriş başarısız. E-posta veya şifre hatalı olabilir.
  Tekrar denemek ister misin?
  [Tekrar Dene 🔄]  [Farklı Bilgi Gir ✏️]
```

### 6.3 Ders Programı Onay Akışı

```
Kullanıcı: [ders_programi.jpg yükler]

Bot: 🔍 Ders programı analiz ediliyor... (typing indicator)

── Arka planda: Vision LLM parsing ──

Bot:
  📚 Ders programından şunları tespit ettim:

  1. ✅ Kariyer Planlama
     📅 Pazartesi 09:00–10:30
     👨‍🏫 Dr. Ahmet Yılmaz
     🖥️ Teams

  2. ✅ Veri Yapıları
     📅 Salı 13:00–14:30
     👨‍🏫 Prof. Ayşe Kaya
     🖥️ Teams

  3. ❓ İngilizce
     📅 Çarşamba 10:00–11:30
     👨‍🏫 Öğr. Gör. John Smith
     🖥️ Belirsiz (Teams?)

  Onaylıyor musun?
  [Tümünü Onayla ✅]  [Düzenle ✏️]  [Baştan Al 🔄]

── Kullanıcı düzenle derse ──
Bot:
  Hangi dersi düzenlemek istiyorsun?
  [Kariyer Planlama]  [Veri Yapıları]  [İngilizce]  [Ders Ekle +]

── Kullanıcı tümünü onaylarsa ──
Bot:
  🎉 Harika! 3 ders kaydedildi.
  
  Sistem her ders başlamadan 5 dakika önce otomatik olarak
  harekete geçecek. Derse girildiğinde sana bildirim göndereceğim.
  
  Yönetim komutları:
  /status  — aktif oturumu gör
  /cancel  — aktif oturumu iptal et
  /courses — derslerini listele
  /reauth  — kimlik doğrulamayı yenile
```

### 6.4 Aktif Oturum Bildirimleri

```
── Ders saatinden 5dk önce ──
Bot: ⏰ Kariyer Planlama dersin 5 dakika sonra başlıyor.
     DYS'ye giriş yapılıyor...

── DYS giriş başarılı (screenshot) ──
Bot: [SCREENSHOT]
     ✅ DYS'ye giriş yapıldı.

── Ders linki bulundu (screenshot) ──
Bot: [SCREENSHOT]
     🔗 Ders linki bulundu, Teams'e yönleniliyor...

── Teams'e girildi (screenshot) ──
Bot: [SCREENSHOT]
     🎓 Kariyer Planlama dersine katıldın!
     ⏱️ Ders bitiş saati: 10:30
     
     [Oturumu İptal Et ✗]

── MFA gerektiğinde ──
Bot: ⚠️ Microsoft doğrulama istiyor!
     Telefonuna SMS/bildirim geldiyse kodu buraya yaz.
     (60 saniye içinde yanıt ver)
     
     Yanıt gelmezse otomatik iptal edilecek.

── Ders bittiğinde ──
Bot: ✅ Kariyer Planlama dersi tamamlandı.
     ⏱️ Süre: 1 saat 28 dakika
     📊 Oturum başarıyla kapatıldı.
```

### 6.5 Yönetim Komutları

| Komut | Açıklama |
|---|---|
| `/start` | Onboarding başlat |
| `/status` | Aktif oturumu göster |
| `/courses` | Kayıtlı dersleri listele/düzenle |
| `/cancel` | Aktif oturumu durdur |
| `/reauth` | Credential yenile (cookie expire durumu) |
| `/schedule` | Bu hafta/bugün dersleri göster |
| `/pause` | Otomasyonu geçici durdur |
| `/resume` | Otomasyonu devam ettir |
| `/logs` | Son 5 oturumun özetini göster |
| `/help` | Komut listesi |

---

## 7. Credential Toplama & Güvenlik

### 7.1 Şifreleme Mimarisi

```python
# src/security/encryption.py

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import os

class CredentialVault:
    """
    Her kullanıcı için Telegram user_id + master key'den türetilmiş
    unique encryption key kullanılır.
    Master key .env'de yaşar, asla DB'ye yazılmaz.
    """
    
    def __init__(self, master_key: bytes):
        self.master_key = master_key
    
    def _derive_key(self, user_id: int) -> bytes:
        """Kullanıcıya özel key türet."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=str(user_id).encode(),
            iterations=480_000,  # OWASP 2024 önerisi
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.master_key))
        return key
    
    def encrypt(self, user_id: int, plaintext: str) -> bytes:
        f = Fernet(self._derive_key(user_id))
        return f.encrypt(plaintext.encode())
    
    def decrypt(self, user_id: int, ciphertext: bytes) -> str:
        f = Fernet(self._derive_key(user_id))
        return f.decrypt(ciphertext).decode()
    
    def encrypt_cookies(self, user_id: int, cookies: list[dict]) -> bytes:
        import json
        return self.encrypt(user_id, json.dumps(cookies))
    
    def decrypt_cookies(self, user_id: int, ciphertext: bytes) -> list[dict]:
        import json
        return json.loads(self.decrypt(user_id, ciphertext))
```

### 7.2 Kullanıcı Mesaj Silme

Şifre içeren kullanıcı mesajları ve bot'un "şifreni yaz" mesajı gönderildikten hemen sonra silinmeli:

```python
# src/bot/handlers/credentials.py

async def handle_password_input(update, context):
    password = update.message.text
    user_id = update.effective_user.id
    
    # 1. Hemen sil
    await update.message.delete()
    
    # 2. "Şifreni yaz" mesajını da sil
    prompt_msg_id = context.user_data.get("password_prompt_msg_id")
    if prompt_msg_id:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=prompt_msg_id
        )
    
    # 3. Şifrele ve kaydet
    vault = context.bot_data["vault"]
    encrypted = vault.encrypt(user_id, password)
    await credential_repo.save_password(user_id, encrypted)
    
    # 4. Devam et
    await update.effective_chat.send_message("✅ Şifre güvenli şekilde kaydedildi.")
```

### 7.3 Cookie Persistence Stratejisi

Microsoft session cookie'leri genellikle **90 gün** geçerlidir (kuruma bağlı). Akış:

```
İlk giriş:
  → Playwright ile DYS/Teams login
  → MFA tamamlanır
  → context.storage_state() ile cookies JSON alınır
  → Şifreli şekilde DB'ye kaydedilir
  → cookie_expires_at = NOW() + 85 days (5 gün marj)

Sonraki girişler:
  → DB'den cookies decrypt edilir
  → Playwright context'e load edilir: context.add_cookies(cookies)
  → Login sayfası açılmaz, direkt DYS'ye gidilir

Cookie expire kontrolü (scheduler):
  → Her gün 08:00'de: cookie_expires_at < NOW() + 7 days olan kullanıcılara
  → Bildirim: "Oturum 7 gün içinde sona eriyor, /reauth ile yenile"
```

---

## 8. Vision LLM — Ders Programı Parsing

### 8.1 Parser Modülü (`src/vision/schedule_parser.py`)

```python
import anthropic
import base64
import json
from pydantic import BaseModel
from typing import Literal
from src.vision.prompts import SCHEDULE_PARSE_PROMPT

class ParsedCourse(BaseModel):
    ders_adi: str
    gun: Literal["Pazartesi","Salı","Çarşamba","Perşembe","Cuma","Cumartesi","Pazar"]
    baslangic_saati: str          # "09:00"
    bitis_saati: str              # "10:30"
    ogretim_uyesi: str | None
    platform: Literal["teams", "zoom", "meet", "unknown"]
    online_mi: bool | None        # None = belirsiz
    guvven_skoru: float           # 0.0–1.0, LLM'in kendi tahmini

class ScheduleParseResult(BaseModel):
    courses: list[ParsedCourse]
    raw_text: str                 # LLM'in okuduğu ham metin
    parse_warnings: list[str]     # Belirsiz alanlar için uyarılar

async def parse_schedule_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg"
) -> ScheduleParseResult:
    
    client = anthropic.AsyncAnthropic()
    
    response = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": base64.standard_b64encode(image_bytes).decode()
                    }
                },
                {
                    "type": "text",
                    "text": SCHEDULE_PARSE_PROMPT
                }
            ]
        }]
    )
    
    # JSON parse (```json bloğunu temizle)
    raw = response.content[0].text
    json_str = extract_json_block(raw)
    data = json.loads(json_str)
    
    return ScheduleParseResult(**data)
```

### 8.2 Prompt (`src/vision/prompts.py`)

```python
SCHEDULE_PARSE_PROMPT = """
Bu görsel bir üniversite ders programıdır.

GÖREVİN:
Görseldeki TÜM dersleri tespit et. Her ders için aşağıdaki JSON formatını kullan.

ÖNEMLI KURALLAR:
1. Sadece "Online", "Uzaktan", "Teams", "Zoom", "Meet" gibi ifadeler içeren veya
   derslik bilgisi OLMAYAN dersleri online_mi: true olarak işaretle.
2. "Derslik: A101" gibi fiziksel yer bilgisi olan dersler online_mi: false.
3. Belirsiz durumlar için online_mi: null kullan.
4. Platform tespiti için ders adı, açıklama veya yer bilgisinde
   "Teams", "Zoom", "Meet" ara. Bulamazsan "unknown".
5. Saat formatı her zaman "HH:MM" (24 saat).
6. Güven skoru: Okuyamadığın, bulanık veya kısmi gördüğün alanlar için düşük ver.

ÇIKTI FORMATI (yalnızca geçerli JSON, markdown code block içinde):
```json
{
  "courses": [
    {
      "ders_adi": "Kariyer Planlama",
      "gun": "Pazartesi",
      "baslangic_saati": "09:00",
      "bitis_saati": "10:30",
      "ogretim_uyesi": "Dr. Ahmet Yılmaz",
      "platform": "teams",
      "online_mi": true,
      "guvven_skoru": 0.95
    }
  ],
  "raw_text": "Görselden okunan ham metin...",
  "parse_warnings": ["İngilizce dersinin platformu okunamadı"]
}
```
"""
```

---

## 9. Web Agent Core

### 9.1 Task Builder (`src/agent/task_builder.py`)

```python
def build_dys_to_teams_task(
    course_name: str,
    dys_url: str,
    username: str,
    password: str,
    end_time: str,
    direct_url: str | None = None,
    dys_search_hint: str | None = None
) -> str:
    
    # Eğer direkt link varsa DYS'yi atla
    if direct_url:
        return f"""
        GÖREV: {course_name} dersine katıl.
        
        ADIM 1: {direct_url} adresine git.
        ADIM 2: "Web'de devam et" veya "Web'de Katıl" seçeneğini seç.
                "Uygulamada Aç" modalı gelirse KAPAT veya "Web'de devam et"e bas.
        ADIM 3: Toplantıya katıl (kamera ve mikrofon KAPALI olarak).
        ADIM 4: CHECKPOINT → screenshot al, 'derse_girildi' olarak işaretle.
        ADIM 5: Saat {end_time} olana kadar sayfada kal. Her 60 saniyede bir
                herhangi bir yerde ufak bir scroll yap.
        ADIM 6: {end_time} olduğunda görevi tamamla.
        
        HATA DURUMU: Giriş başarısız olursa HATA_KODU: JOIN_FAILED döndür.
        MFA DURUMU: SMS/authenticator kodu istenirse HATA_KODU: MFA_REQUIRED döndür.
        """
    
    # DYS üzerinden bulma akışı
    search_context = f"Ders adı '{dys_search_hint or course_name}' ile ara." if dys_search_hint else ""
    
    return f"""
    GÖREV: {course_name} dersine DYS üzerinden katıl.
    
    === AŞAMA 1: DYS GİRİŞİ ===
    ADIM 1: {dys_url} adresine git.
    ADIM 2: Giriş formunu bul. Kullanıcı adı '{username}', şifre ile giriş yap.
    ADIM 3: Giriş başarılıysa CHECKPOINT → screenshot al, 'dys_login' olarak işaretle.
            Başarısız → HATA_KODU: DYS_LOGIN_FAILED
    
    === AŞAMA 2: DERS LİNKİ BULMA ===
    ADIM 4: "Derslerim", "Ders Programı", "Öğrenci Paneli" gibi bir bölüm bul.
    ADIM 5: {course_name} dersini bul. {search_context}
    ADIM 6: Dersin sayfasına gir.
    ADIM 7: "Canlı Ders", "Derse Katıl", "Teams", "Zoom", "Toplantıya Katıl",
            "Join Meeting" gibi bir link veya buton ara.
            Bulunamadı → HATA_KODU: LINK_NOT_FOUND
    ADIM 8: Linki bulduysan CHECKPOINT → screenshot al, 'ders_link_bulundu' olarak işaretle.
    
    === AŞAMA 3: DERSE KATILMA ===
    ADIM 9: Linke tıkla.
    ADIM 10: Teams/Zoom web arayüzü açıldıysa:
             - "Uygulamada Aç" modalı → KAPAT veya "Web'de devam et"e tıkla
             - Kamera/mikrofon izin isterlerse REDDET
             - "Katıl" / "Join" butonuna bas
    ADIM 11: Derse girildikten sonra CHECKPOINT → screenshot al, 'derse_girildi' olarak işaretle.
    
    === AŞAMA 4: DERSE DEVAM ===
    ADIM 12: Saat {end_time} olana kadar sayfada kal.
             Her 45–90 saniyede bir sayfada küçük bir mouse hareketi yap.
             Herhangi bir popup/modal gelirse KAPAT.
    ADIM 13: {end_time}'da görevi tamamla, CHECKPOINT → 'ders_tamamlandi'.
    
    KRİTİK KURALLAR:
    - Asla mikrofonu veya kamerayı açma.
    - MFA/2FA kodu istenirse hemen dur: HATA_KODU: MFA_REQUIRED
    - Sayfa donarsa: bir kez yenile. İki kez donmarsa: HATA_KODU: PAGE_FROZEN
    - Teams'te "toplantıdan ayrıl" butonuna ASLA tıklama.
    """
```

### 9.2 Agent Runner (`src/agent/runner.py`)

```python
import asyncio
from browser_use import Agent
from langchain_anthropic import ChatAnthropic
from src.agent.checkpoints import CheckpointHandler
from src.agent.mfa_handler import MFAHandler
from src.core.exceptions import (
    AgentLoginFailed, AgentLinkNotFound,
    AgentMFARequired, AgentPageFrozen, AgentJoinFailed
)

class AgentRunner:
    
    def __init__(
        self,
        session_id: str,
        user_id: int,
        notifier,         # NotificationService instance
        vault,            # CredentialVault instance
        redis_client
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.notifier = notifier
        self.vault = vault
        self.redis = redis_client
    
    async def run(self, task: str, course_name: str) -> dict:
        
        checkpoint_handler = CheckpointHandler(
            session_id=self.session_id,
            notifier=self.notifier,
            user_id=self.user_id
        )
        
        # Model seçimi config'den gelir
        if settings.AGENT_LLM_PROVIDER == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", temperature=0)
        else:
            llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
        
        mfa_handler = MFAHandler(
            user_id=self.user_id,
            redis=self.redis,
            notifier=self.notifier
        )
        
        agent = Agent(
            task=task,
            llm=llm,
            # browser-use callback hook'ları
            on_step=checkpoint_handler.handle_step,
        )
        
        try:
            result = await asyncio.wait_for(
                agent.run(),
                timeout=3600  # 1 saat max (en uzun ders)
            )
            
            # Sonucu parse et
            return self._parse_result(result)
            
        except asyncio.TimeoutError:
            raise AgentPageFrozen("Agent 1 saat içinde tamamlanamadı")
    
    def _parse_result(self, raw_result) -> dict:
        result_text = str(raw_result)
        
        if "HATA_KODU: DYS_LOGIN_FAILED" in result_text:
            raise AgentLoginFailed("DYS giriş başarısız")
        if "HATA_KODU: LINK_NOT_FOUND" in result_text:
            raise AgentLinkNotFound("Ders linki DYS'de bulunamadı")
        if "HATA_KODU: MFA_REQUIRED" in result_text:
            raise AgentMFARequired("MFA doğrulaması gerekiyor")
        if "HATA_KODU: JOIN_FAILED" in result_text:
            raise AgentJoinFailed("Derse katılım başarısız")
        
        return {"status": "completed", "raw": result_text}
```

### 9.3 Checkpoint Handler (`src/agent/checkpoints.py`)

```python
CHECKPOINTS = {
    "dys_login": {
        "message": "✅ DYS'ye başarıyla giriş yapıldı.",
        "emoji": "🔐"
    },
    "ders_link_bulundu": {
        "message": "🔗 Ders linki bulundu, Teams'e yönleniliyor...",
        "emoji": "🔗"
    },
    "derse_girildi": {
        "message": "🎓 Derse başarıyla katıldın! Ders süresince burada olacağım.",
        "emoji": "🎓"
    },
    "ders_tamamlandi": {
        "message": "✅ Ders tamamlandı. Oturum kapatılıyor.",
        "emoji": "✅"
    }
}
```

---

## 10. Senaryo Matrisi

Her senaryo için agent'ın ne yapacağı, kullanıcıya ne bildireceği tanımlıdır.

### 10.1 Happy Path

```
[Tetikleyici] Ders saatinden 5dk önce scheduler
[Akış]        Credential yükle → DYS login → Link bul → Teams → Derse gir → Bekle → Bildir
[Bildirim]    3 aşamada screenshot + tamamlanma mesajı
[Sonuç]       session.status = 'completed'
```

### 10.2 DYS Login Başarısız

```
[Tetikleyici] DYS yanlış credential veya hesap kilitli
[Akış]        Login dene → 3 kez başarısız → Dur
[Bildirim]    "❌ DYS'ye giriş yapılamadı. /reauth ile şifreni güncelle."
[Sonuç]       session.status = 'failed', failure_reason = 'DYS_LOGIN_FAILED'
[Retry]       Kullanıcı /reauth yaparsa aynı ders için tekrar denenebilir
```

### 10.3 Cookie Expire

```
[Tetikleyici] cookie_expires_at < NOW()
[Akış]        Saved cookie ile login dene → Redirect login sayfasına gidince anla
[Bildirim]    "⚠️ Oturumun sona erdi. /reauth ile yenile. Ders X dakika sonra başlıyor."
[Sonuç]       session.status = 'pending' (reauth bekleniyor)
```

### 10.4 MFA — SMS Kodu

```
[Tetikleyici] Microsoft SMS kodu ister
[Akış]        Agent durur → HATA_KODU: MFA_REQUIRED emit eder
[Bildirim]    "⚠️ Microsoft SMS kodu istedi! Kodu buraya yaz (60sn):"
[Kullanıcı]   "123456" yazar
[Akış devam]  Redis'e kod yazılır → Agent okur → Forma girer → Devam eder
[Timeout]     60sn içinde kod gelmezse: session.status = 'failed', "⏰ Zaman aşımı"
```

### 10.5 MFA — Microsoft Authenticator Push

```
[Tetikleyici] Microsoft Authenticator push bildirimi ister
[Akış]        Agent durur
[Bildirim]    "📱 Telefonundaki Microsoft Authenticator'dan onay ver, sonra /confirmed yaz."
[Kullanıcı]   Telefonda onaylar, /confirmed yazar
[Akış devam]  Agent kontrol eder, devam eder
[Timeout]     120sn: "⏰ Onay alınamadı. Session iptal edildi."
```

### 10.6 DYS'de Link Bulunamadı

```
[Tetikleyici] Ders DYS'de yok veya canlı ders linki paylaşılmamış
[Akış]        Agent tüm olası yerlere bakar (duyurular, mesajlar, ders sayfası) → Bulamaz
[Bildirim]    "🔍 DYS'de 'Kariyer Planlama' için canlı ders linki bulunamadı.
               Direkt Teams linkini /add_link komutuyla ekleyebilirsin."
[Sonuç]       session.status = 'failed', failure_reason = 'LINK_NOT_FOUND'
```

### 10.7 Toplantı Henüz Aktif Değil (Hoca Başlatmamış)

```
[Tetikleyici] Teams linkine gidildi, toplantı "başlamadı" durumunda
[Akış]        Agent 10dk boyunca her 2dk'da bir sayfayı yeniler
[Bildirim]    "⏳ Toplantı henüz başlamamış. 10 dakika denemeye devam edeceğim."
[Başlarsa]    Normal happy path devam eder
[Başlamazsa]  10dk sonra: "❌ Toplantı başlamadı. session iptal edildi."
[Sonuç]       session.status = 'failed', failure_reason = 'MEETING_NOT_STARTED'
```

### 10.8 Ders Süresince Agent Crash

```
[Tetikleyici] Playwright/browser unexpected crash
[Akış]        Exception yakalanır → session.status = 'failed' → Retry logic
[Retry]       retry_count < 3 ise: 2 dakika bekle, yeniden başlat
              retry_count >= 3 ise: kullanıcıya bildir
[Bildirim]    "⚠️ Beklenmedik bir hata oluştu. Yeniden bağlanılıyor (2/3)..."
              veya: "❌ 3 denemede de bağlanılamadı. Manuel katılman gerekiyor."
```

### 10.9 Kullanıcı Manuel İptal

```
[Tetikleyici] Kullanıcı /cancel yazar
[Akış]        Redis'e CANCEL_FLAG set edilir → Agent kontrol eder → Playwright kapatılır
[Bildirim]    "⏹️ Oturum iptal edildi. (X dakika aktifti)"
[Sonuç]       session.status = 'cancelled'
```

### 10.10 Kullanıcı /pause Yazar (Tüm Dersler İçin)

```
[Tetikleyici] /pause komutu
[Akış]        Aktif session varsa onu sonlandır, tüm scheduled job'ları devre dışı bırak
[Bildirim]    "⏸️ GhostAttend duraklatıldı. /resume ile devam edebilirsin."
[Sonuç]       Kullanıcı user.is_active = False
```

---

## 11. Scheduler Sistemi

### 11.1 Job Yönetimi (`src/scheduler/job_manager.py`)

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

def create_scheduler() -> AsyncIOScheduler:
    jobstores = {
        "default": RedisJobStore(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=1  # Scheduler için ayrı Redis DB
        )
    }
    executors = {"default": AsyncIOExecutor()}
    
    return AsyncIOScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults={
            "coalesce": True,        # Gecikmiş job'ları birleştir
            "max_instances": 1,      # Aynı job'dan iki tane çalışmasın
            "misfire_grace_time": 300  # 5dk içinde tetiklenen gecikmiş job çalışır
        },
        timezone="Europe/Istanbul"
    )

def schedule_course(scheduler, course, user_id):
    """Bir ders için haftalık tekrar eden job oluştur."""
    
    # Ders saatinden 5dk önce tetikle
    trigger_time = subtract_minutes(course.start_time, 5)
    
    scheduler.add_job(
        func="src.scheduler.tasks:execute_attendance",
        trigger="cron",
        id=f"course_{course.id}",
        replace_existing=True,
        day_of_week=DAYS[course.day_of_week],  # 'mon', 'tue', ...
        hour=trigger_time.hour,
        minute=trigger_time.minute,
        kwargs={
            "user_id": user_id,
            "course_id": str(course.id)
        }
    )
```

### 11.2 Günlük Cookie Kontrolü

```python
# Her gün 08:00'de çalışır
scheduler.add_job(
    func="src.scheduler.tasks:check_cookie_expirations",
    trigger="cron",
    id="daily_cookie_check",
    hour=8,
    minute=0
)
```

---

## 12. Bildirim Servisi

### 12.1 Notifier (`src/notifications/telegram_notifier.py`)

```python
class TelegramNotifier:
    
    async def send_screenshot(
        self,
        user_id: int,
        screenshot_bytes: bytes,
        caption: str,
        checkpoint_name: str,
        session_id: str
    ):
        # Screenshot'ı gönder ve file_id'yi cache'le (Telegram'a aynı dosyayı tekrar upload etme)
        cached_file_id = await self._get_cached_file_id(session_id, checkpoint_name)
        
        if cached_file_id:
            msg = await self.bot.send_photo(
                chat_id=user_id,
                photo=cached_file_id,
                caption=caption
            )
        else:
            msg = await self.bot.send_photo(
                chat_id=user_id,
                photo=screenshot_bytes,
                caption=caption
            )
            await self._cache_file_id(
                session_id, checkpoint_name,
                msg.photo[-1].file_id
            )
        
        # DB'ye kaydet
        await notification_repo.save(user_id, session_id, "screenshot", caption)
    
    async def send_error(self, user_id: int, error_code: str, details: str = ""):
        templates = {
            "DYS_LOGIN_FAILED": "❌ DYS'ye giriş yapılamadı. /reauth ile şifreni güncelle.",
            "LINK_NOT_FOUND": f"🔍 Ders linki DYS'de bulunamadı.\n/add_link ile direkt link ekleyebilirsin.",
            "MFA_REQUIRED": "⚠️ Microsoft doğrulama istiyor! Kodu aşağıya yaz:",
            "PAGE_FROZEN": "⚠️ Sayfa dondu, yeniden bağlanılıyor...",
            "JOIN_FAILED": "❌ Derse katılım başarısız. Tekrar deneniyor...",
            "MEETING_NOT_STARTED": "⏳ Toplantı henüz başlatılmamış. Bekleniyor...",
            "MAX_RETRY_EXCEEDED": "❌ 3 denemede de bağlanılamadı. Manuel katılman gerekiyor.",
        }
        message = templates.get(error_code, f"❌ Beklenmedik hata: {error_code}")
        if details:
            message += f"\n\n`{details}`"
        
        await self.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
```

---

## 13. Docker & Deployment

### 13.1 `docker-compose.yml` (Production)

```yaml
version: "3.9"

services:
  bot:
    build:
      context: .
      dockerfile: docker/Dockerfile.bot
    restart: unless-stopped
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./logs:/app/logs
    networks:
      - ghost_net

  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    restart: unless-stopped
    env_file: .env
    depends_on:
      - redis
      - postgres
    volumes:
      - ./logs:/app/logs
      - ./screenshots:/app/screenshots
    networks:
      - ghost_net
    deploy:
      resources:
        limits:
          memory: 2G    # Browser instance başına ~400MB

  scheduler:
    build:
      context: .
      dockerfile: docker/Dockerfile.bot  # Aynı image, farklı CMD
    command: python -m src.scheduler.main
    restart: unless-stopped
    env_file: .env
    depends_on:
      - redis
      - postgres
    networks:
      - ghost_net

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ghostattend
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - ghost_net

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - ghost_net

  nginx:
    image: nginx:alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./docker/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - bot
    networks:
      - ghost_net

volumes:
  postgres_data:
  redis_data:

networks:
  ghost_net:
    driver: bridge
```

### 13.2 `docker/Dockerfile.bot`

```dockerfile
FROM python:3.11-slim-bookworm

# Sistem bağımlılıkları (Playwright için)
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    fonts-liberation libappindicator3-1 libasound2 libatk-bridge2.0-0 \
    libatk1.0-0 libcups2 libdbus-1-3 libgdk-pixbuf2.0-0 libnspr4 \
    libnss3 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 \
    xdg-utils libxss1 libgbm1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Poetry ile bağımlılık yönetimi
COPY pyproject.toml poetry.lock ./
RUN pip install poetry==1.8.3 && \
    poetry config virtualenvs.create false && \
    poetry install --no-dev --no-interaction

# Playwright browser'ları yükle (sadece chromium, boyut optimizasyonu)
RUN playwright install chromium && playwright install-deps chromium

COPY src/ ./src/
COPY alembic.ini ./

# Non-root kullanıcı (güvenlik)
RUN useradd -m -u 1000 ghostuser && chown -R ghostuser:ghostuser /app
USER ghostuser

CMD ["python", "-m", "src.bot.main"]
```

### 13.3 `docker-compose.dev.yml`

```yaml
version: "3.9"

services:
  bot:
    build:
      context: .
      dockerfile: docker/Dockerfile.bot
    volumes:
      - ./src:/app/src  # Hot reload için mount
    environment:
      - ENVIRONMENT=development
      - LOG_LEVEL=DEBUG
    command: python -m src.bot.main

  worker:
    volumes:
      - ./src:/app/src
    environment:
      - ENVIRONMENT=development

  # Test için sahte DYS sunucusu
  mock_dys:
    build:
      context: ./tests/e2e/fixtures/mock_dys_server
    ports:
      - "8888:8888"
```

### 13.4 `scripts/setup.sh`

```bash
#!/bin/bash
set -e

echo "🚀 GhostAttend kurulumu başlıyor..."

# .env oluştur
if [ ! -f .env ]; then
    cp .env.example .env
    # Master encryption key üret
    MASTER_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    sed -i "s/MASTER_ENCRYPTION_KEY=.*/MASTER_ENCRYPTION_KEY=$MASTER_KEY/" .env
    echo "✅ .env oluşturuldu. Lütfen TELEGRAM_BOT_TOKEN ve diğer değerleri girin."
    exit 1
fi

# Docker build + migration + başlat
docker compose build
docker compose up -d postgres redis
sleep 5
docker compose run --rm bot alembic upgrade head
docker compose up -d
echo "✅ GhostAttend çalışıyor!"
```

---

## 14. CI/CD Pipeline

### 14.1 `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: ghostattend_test
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
        ports:
          - 5432:5432
      
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      
      - name: Install Playwright
        run: poetry run playwright install chromium --with-deps
      
      - name: Lint (Ruff)
        run: poetry run ruff check src/ tests/
      
      - name: Type check (mypy)
        run: poetry run mypy src/
      
      - name: Run tests
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/ghostattend_test
          REDIS_URL: redis://localhost:6379/0
          MASTER_ENCRYPTION_KEY: ${{ secrets.TEST_MASTER_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TEST_TELEGRAM_BOT_TOKEN }}
        run: |
          poetry run pytest tests/unit tests/integration \
            --cov=src \
            --cov-report=xml \
            --cov-fail-under=75 \
            -v
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Safety (dependency vulnerabilities)
        run: |
          pip install safety
          safety check --full-report
      - name: Run Bandit (code security)
        run: |
          pip install bandit
          bandit -r src/ -ll
```

### 14.2 `.github/workflows/cd.yml`

```yaml
name: CD

on:
  push:
    branches: [main]
    tags:
      - 'v*'

jobs:
  deploy:
    runs-on: ubuntu-latest
    needs: [test]  # CI geçmeden deploy olmaz
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Deploy to VPS
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /opt/ghost-attend
            git pull origin main
            docker compose pull
            docker compose build
            docker compose run --rm bot alembic upgrade head
            docker compose up -d --no-deps bot worker scheduler
            docker system prune -f
            echo "✅ Deploy tamamlandı: $(date)"
```

---

## 15. Test Stratejisi (TDD)

### 15.1 Katman Katman Test Yaklaşımı

```
Unit Tests    → Saf fonksiyon testleri (DB yok, dış servis yok)
Integration   → Gerçek DB + Redis, mock LLM + mock Telegram
E2E           → Gerçek browser + local mock DYS sunucusu
```

### 15.2 Örnek Unit Test: Schedule Parser

```python
# tests/unit/test_schedule_parser.py
import pytest
from unittest.mock import AsyncMock, patch
from src.vision.schedule_parser import parse_schedule_image, ScheduleParseResult

MOCK_CLAUDE_RESPONSE = """
```json
{
  "courses": [
    {
      "ders_adi": "Kariyer Planlama",
      "gun": "Pazartesi",
      "baslangic_saati": "09:00",
      "bitis_saati": "10:30",
      "ogretim_uyesi": "Dr. Ahmet Yılmaz",
      "platform": "teams",
      "online_mi": true,
      "guvven_skoru": 0.95
    }
  ],
  "raw_text": "Ders programı",
  "parse_warnings": []
}
```
"""

@pytest.mark.asyncio
async def test_parse_schedule_returns_online_courses():
    with patch("anthropic.AsyncAnthropic") as mock_client:
        mock_client.return_value.messages.create = AsyncMock(
            return_value=MockAnthropicResponse(MOCK_CLAUDE_RESPONSE)
        )
        
        result = await parse_schedule_image(b"fake_image_bytes")
        
        assert isinstance(result, ScheduleParseResult)
        assert len(result.courses) == 1
        assert result.courses[0].ders_adi == "Kariyer Planlama"
        assert result.courses[0].online_mi is True
        assert result.courses[0].platform == "teams"

@pytest.mark.asyncio
async def test_parse_schedule_handles_malformed_json():
    with patch("anthropic.AsyncAnthropic") as mock_client:
        mock_client.return_value.messages.create = AsyncMock(
            return_value=MockAnthropicResponse("Bu geçerli JSON değil")
        )
        
        with pytest.raises(ValueError, match="JSON parse"):
            await parse_schedule_image(b"fake_image_bytes")
```

### 15.3 Örnek Integration Test: Bot Onboarding Akışı

```python
# tests/integration/test_bot_flows.py
import pytest
from telegram.ext import Application
from tests.helpers import BotTestClient, make_fake_update

@pytest.mark.asyncio
async def test_onboarding_happy_path(bot_client: BotTestClient, db_session):
    user_id = 123456789
    
    # /start komutu
    response = await bot_client.send_command("/start", user_id=user_id)
    assert "Kuruluma Başla" in response.text
    
    # DYS URL girişi
    response = await bot_client.send_message(
        "https://obs.ege.edu.tr", user_id=user_id
    )
    assert "E-posta" in response.text
    
    # Email girişi
    response = await bot_client.send_message(
        "123456@stu.ege.edu.tr", user_id=user_id
    )
    assert "Şifreni yaz" in response.text
    
    # Şifre girişi (mock DYS login başarılı varsayılıyor)
    with patch_dys_login(success=True):
        response = await bot_client.send_message(
            "secret123", user_id=user_id
        )
    
    # Kullanıcı mesajı silindi mi?
    assert bot_client.deleted_message_ids  # delete_message çağrıldı
    assert "ders programını yükle" in response.text.lower()

@pytest.mark.asyncio
async def test_credential_encryption_roundtrip(vault):
    user_id = 999
    original = "super_secret_password"
    
    encrypted = vault.encrypt(user_id, original)
    decrypted = vault.decrypt(user_id, encrypted)
    
    assert decrypted == original
    assert encrypted != original.encode()  # plaintext değil
```

### 15.4 Test Coverage Hedefleri

| Katman | Minimum Coverage |
|---|---|
| `src/security/` | %95 |
| `src/vision/` | %85 |
| `src/agent/task_builder.py` | %90 |
| `src/bot/handlers/` | %80 |
| `src/scheduler/` | %80 |
| `src/db/repositories/` | %85 |
| **Genel** | **%75** |

---

## 16. Environment & Config

### 16.1 `.env.example`

```bash
# ── Uygulama ──
ENVIRONMENT=production          # development | production | test
LOG_LEVEL=INFO                  # DEBUG | INFO | WARNING | ERROR

# ── Telegram ──
TELEGRAM_BOT_TOKEN=             # @BotFather'dan alınan token
TELEGRAM_WEBHOOK_URL=           # https://yourdomain.com/webhook (production)
TELEGRAM_WEBHOOK_SECRET=        # Rastgele güçlü string

# ── LLM ──
ANTHROPIC_API_KEY=              # console.anthropic.com
OPENAI_API_KEY=                 # Fallback (opsiyonel)
GOOGLE_API_KEY=                 # aistudio.google.com
AGENT_LLM_PROVIDER=google       # anthropic | google | openai
AGENT_LLM_MODEL=gemini-3.1-flash-lite
VISION_LLM_MODEL=gemini-3.1-flash-lite

# ── Veritabanı ──
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ghostattend
POSTGRES_USER=
POSTGRES_PASSWORD=
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}/${POSTGRES_DB}

# ── Redis ──
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_URL=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/0

# ── Güvenlik ──
MASTER_ENCRYPTION_KEY=          # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ── Agent ──
BROWSER_HEADLESS=true           # Development'ta false yapabilirsin
AGENT_TIMEOUT_SECONDS=3600
AGENT_MAX_RETRY=3
MEETING_START_OFFSET_MINUTES=5  # Dersten kaç dakika önce başlasın

# ── Screenshot ──
SCREENSHOT_STORAGE=local        # local | s3
SCREENSHOT_DIR=/app/screenshots
# S3 kullanılırsa:
# AWS_ACCESS_KEY_ID=
# AWS_SECRET_ACCESS_KEY=
# AWS_S3_BUCKET=
```

### 16.2 Pydantic Settings (`src/core/config.py`)

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"
    
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_URL: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    AGENT_LLM_PROVIDER: str = "google"  # google | openai | anthropic
    AGENT_LLM_MODEL: str = "gemini-3.1-flash-lite" 
    VISION_LLM_MODEL: str = "gemini-3.1-flash-lite"
    
    # Alternatif ucuz modeller (config üzerinden değiştirilebilir)
    # GPT_MODEL: str = "gpt-4o-mini"
    # ANTHROPIC_MODEL: str = "claude-3-5-haiku"
    
    DATABASE_URL: str
    REDIS_URL: str
    
    MASTER_ENCRYPTION_KEY: str
    
    BROWSER_HEADLESS: bool = True
    AGENT_TIMEOUT_SECONDS: int = 3600
    AGENT_MAX_RETRY: int = 3
    MEETING_START_OFFSET_MINUTES: int = 5
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

settings = Settings()
```

---

## 17. Hata Yönetimi & Logging

### 17.1 Exception Hiyerarşisi (`src/core/exceptions.py`)

```python
class GhostAttendError(Exception):
    """Base exception"""
    pass

# Agent hataları
class AgentError(GhostAttendError): pass
class AgentLoginFailed(AgentError): pass
class AgentLinkNotFound(AgentError): pass
class AgentMFARequired(AgentError):
    def __init__(self, mfa_type: str):
        self.mfa_type = mfa_type  # 'sms' | 'authenticator' | 'email'
class AgentJoinFailed(AgentError): pass
class AgentPageFrozen(AgentError): pass
class AgentMaxRetryExceeded(AgentError): pass
class MeetingNotStarted(AgentError): pass

# Credential hataları
class CredentialError(GhostAttendError): pass
class CredentialNotFound(CredentialError): pass
class CredentialDecryptFailed(CredentialError): pass
class CookieExpired(CredentialError): pass

# Vision hataları
class VisionError(GhostAttendError): pass
class ScheduleParseError(VisionError): pass
class LowConfidenceParseError(VisionError):
    def __init__(self, low_confidence_courses: list):
        self.courses = low_confidence_courses
```

### 17.2 Structured Logging

```python
# src/core/logging.py
import structlog

def configure_logging(log_level: str):
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()  # Production: JSON
            # structlog.dev.ConsoleRenderer()    # Development: renkli
        ],
        logger_factory=structlog.PrintLoggerFactory()
    )

# Kullanım:
log = structlog.get_logger()

async def run_agent(session_id: str, user_id: int):
    log = structlog.get_logger().bind(
        session_id=session_id,
        user_id=user_id
    )
    log.info("agent.start")
    # ...
    log.info("agent.checkpoint", checkpoint="dys_login")
    log.error("agent.failed", error="DYS_LOGIN_FAILED", retry=1)
```

---

## 18. Açık Kaynak Standartları

### 18.1 Lisans

**MIT Lisansı** — Kopyalama, değiştirme, dağıtma serbesttir.

### 18.2 README.md Zorunlu Bölümleri

```markdown
# GhostAttend

> ⚠️ SORUMLULUK REDDİ: Bu araç Microsoft ToS ve bazı üniversite yönetmeliklerine
> aykırı kullanılabilir. Kullanıcı tüm sorumluluğu üstlenir.

## Özellikler
## Gereksinimler (VPS, Docker, API key)
## Kurulum (setup.sh veya adım adım)
## Konfigürasyon (.env açıklaması)
## Telegram Bot Kullanımı
## Katkıda Bulunma
## Güvenlik Bildirimi (SECURITY.md)
## Lisans
```

### 18.3 `SECURITY.md`

Güvenlik açığı bildirimi için özel email adresi veya GitHub Private Vulnerability Reporting kullanılmalı. Credentials ile ilgili herhangi bir güvenlik açığı **72 saat içinde** yanıtlanmalı.

### 18.4 Katkı Kuralları

```markdown
# CONTRIBUTING.md

## Branch stratejisi
main     → production
develop  → aktif geliştirme
feature/ → yeni özellik
fix/     → bug fix
docs/    → dokümantasyon

## PR kuralları
- Tüm CI geçmeli
- En az 1 reviewer onayı
- Test coverage düşürülemez
- Commit mesajları: Conventional Commits formatı
  feat: ders programı düzenleme akışı eklendi
  fix: cookie expiry bildirimi tetiklenmiyordu
  test: DYS login integration testi eklendi
```

---

## 19. Yol Haritası (MVP → v1.0)

### Sprint 1 — Temel Altyapı (1-2 hafta)
- [ ] Repo + Docker + CI/CD iskelet
- [ ] Veritabanı şeması + Alembic migration
- [ ] Telegram bot skeleton (`/start`, FSM state machine)
- [ ] Credential toplama + şifreleme + silme akışı
- [ ] `CredentialVault` unit testleri

### Sprint 2 — Vision Parsing (1 hafta)
- [ ] Ders programı image → ParsedCourse JSON
- [ ] Telegram'da onay akışı (inline keyboard)
- [ ] Manuel düzenleme akışı (düşük güvenli dersler)
- [ ] Parser unit testleri (farklı üniversite formatları)

### Sprint 3 — Web Agent Core (2 hafta)
- [ ] `browser-use` + Playwright entegrasyonu
- [ ] `AgentRunner` + task builder
- [ ] Checkpoint + screenshot pipeline
- [ ] Cookie persistence + yükleme
- [ ] Mock DYS sunucusu (test için)
- [ ] Agent integration testleri

### Sprint 4 — MFA & Senaryo Handling (1 hafta)
- [ ] SMS MFA interrupt akışı
- [ ] Authenticator push akışı
- [ ] Tüm senaryo matrisi implementasyonu
- [ ] Retry logic
- [ ] Session 10 senaryo üzerinde test

### Sprint 5 — Scheduler & Bildirim (1 hafta)
- [ ] APScheduler + Redis job store
- [ ] Cookie expiry günlük kontrolü
- [ ] Bildirim servisinin tamamlanması
- [ ] `/status`, `/cancel`, `/pause`, `/resume`

### Sprint 6 — Polish & Release (1 hafta)
- [ ] E2E testler (mock DYS + gerçek benzeri akış)
- [ ] README + SETUP.md + demo video
- [ ] GitHub release v1.0.0
- [ ] Docker Hub image publish

---

## Appendix A — Makefile

```makefile
.PHONY: dev test lint typecheck migrate setup

dev:
	docker compose -f docker-compose.dev.yml up

test:
	poetry run pytest tests/unit tests/integration -v --cov=src

test-e2e:
	docker compose -f docker-compose.test.yml up --abort-on-container-exit

lint:
	poetry run ruff check src/ tests/ --fix

typecheck:
	poetry run mypy src/

migrate:
	docker compose run --rm bot alembic upgrade head

makemigration:
	docker compose run --rm bot alembic revision --autogenerate -m "$(name)"

setup:
	./scripts/setup.sh

logs:
	docker compose logs -f bot worker

shell:
	docker compose exec bot python
```

---

*Bu doküman projenin yaşayan anayasasıdır. Her büyük mimari karar buraya yansıtılmalı, agentic IDE context'i bu dosya üzerinden sağlanmalıdır.*

**Son güncelleme:** Proje başlangıcı
**Versiyon:** 1.0.0-draft