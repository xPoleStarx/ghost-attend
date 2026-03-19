# ghost-attend

Telegram üzerinden konuşan, **LangGraph** + **browser-use** (Playwright) + **Google Gemini** ile web’de görev yapan bot. Giriş / hassas adımlarda durur, ekran görüntüsü ve soru gönderir; yanıtınızla devam eder (HITL).

**Hızlı yol:** depoyu klonla → `.env` doldur → `.\Run.ps1` (Windows) veya `./Run.sh` (Linux/macOS). Aşağıdaki tabloda ayrıntılar var.

---

## Klonladıktan sonra (özet)

| Adım | Ne yapılır |
|------|------------|
| 1 | Depoyu klonla: `git clone …` ve klasöre gir |
| 2 | **Python 3.11+** kur ([python.org](https://www.python.org/downloads/)); Windows’ta **“Add python.exe to PATH”** işaretle |
| 3 | **`.env`** hazırla: `.env.example` → `.env`, içine `TELEGRAM_BOT_TOKEN` ve `GOOGLE_API_KEY` yaz |
| 4 | **Tek komut** betiklerinden birini çalıştır: venv → `pip install -e .` (bağımlılıklar [`pyproject.toml`](pyproject.toml) üzerinden) → Playwright Chromium → import testi → bot |

**Bağımlılıklar:** Tek kaynak [`pyproject.toml`](pyproject.toml). [`requirements.txt`](requirements.txt) yalnızca elle `pip install -r` ile uyumluluk içindir; `Run.ps1` / `Run.sh` **artık** önce `requirements.txt` okumaz (eski dosyanın yanlışlıkla `langchain-google-genai` 2.x’e düşürmesi engellendi).

---

## Otomatik kurulum + çalıştırma (önerilen)

### Windows

PowerShell veya `run.bat`:

```powershell
cd ghost-attend
.\Run.ps1
```

Çift tık: **`run.bat`**

Her çalıştırmada (`-SkipInstall` yokken): `pip install` (idempotent) → Playwright → **`app.main` + `app.agent.task_agent`** import doğrulaması → `.env` yoksa kopyalanır → bot.

- Hızlı başlat (kurulum atla): `.\Run.ps1 -SkipInstall` — yalnızca venv ve paketler zaten tamamsa.
- Tüm paketleri zorla yenile: `.\Run.ps1 -ForceInstall`
- Sadece kurulum: `.\Run.ps1 -InstallOnly` — sonra `.\Run.ps1 -SkipInstall`
- Betik çalışmıyorsa: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
- Python bulunamazsa: `$env:GHOST_ATTEND_PYTHON = "C:\...\python.exe"` sonra `.\Run.ps1`

### Linux / macOS

```bash
cd ghost-attend
chmod +x Run.sh
./Run.sh
```

İsteğe bağlı: `export GHOST_ATTEND_PYTHON=/usr/bin/python3`

Aynı mantık: venv, `requirements.txt`, editable kurulum, Playwright, `.env`, bot.

### Docker (sistemde Python yoksa)

[Docker Desktop](https://www.docker.com/products/docker-desktop/) kurulu olsun; proje kökünde `.env` dolu olsun.

```bash
docker compose up --build
```

---

## Manuel kurulum (IDE / CI / ince ayar)

```bash
cd ghost-attend
python3 -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
# İsterseniz iki aşamalı: pip install -r requirements.txt && pip install -e .
python -m playwright install chromium
copy .env.example .env   # veya cp; .env içini doldur
python -m app.main
# Alternatif (pyproject script): ghost-attend
```

Geliştirici (test): `python -m pip install -e ".[dev]"`

Doğrulama: `python -m pip check` · `python -m pytest` (tests varsa)

---

## Makefile (Linux / macOS, `make` varsa)

```bash
make install    # venv + requirements + editable + playwright + .env şablonu
make run        # bot
make test       # pytest
```

---

## Ortam değişkenleri (`.env`)

| Değişken | Zorunlu | Açıklama |
|----------|---------|----------|
| `TELEGRAM_BOT_TOKEN` | Evet | BotFather token |
| `GOOGLE_API_KEY` | Evet | [Google AI Studio](https://aistudio.google.com/app/apikey) Gemini API anahtarı |
| `GEMINI_MODEL` | Hayır | Varsayılan: `gemini-2.5-flash`. Gemini 3.x kullanıyorsanız `langchain-google-genai>=4.2` gerekir (projede tanımlı); aksi hâlde araç çağrısı sonrası `thought_signature` hatası oluşabilir. |
| `PLAYWRIGHT_HEADLESS` | Hayır | `false` = tarayıcı penceresi (yerel); Docker’da genelde `true` |
| `CHECKPOINT_PATH` | Hayır | LangGraph: SQLite dosyası (`AsyncSqliteSaver`), varsayılan `./data/checkpoints.db` |
| `BROWSER_MAX_STEPS` | Hayır | browser-use üst adım limiti (varsayılan `35`) |
| `BROWSER_STEP_TIMEOUT` | Hayır | Adım zaman aşımı saniye (varsayılan `180`) |

Şablon: [`.env.example`](.env.example)

---

## Mimari (kısa)

| Bileşen | Konum |
|--------|--------|
| Gemini görev ajanı (ReAct, araçlar) | `app/agent/task_agent.py`, `app/agent/tools.py` |
| Araçlar | `run_browser_automation`, `capture_page_screenshot`, `ask_user` (LangGraph `create_react_agent`) |
| browser-use (gömülü tarayıcı) | `app/adapters/browser_use_runner.py` |
| Telegram | `app/telegram/` |
| Checkpoint | `app/persistence/checkpointer.py` — `CHECKPOINT_PATH` (varsayılan `./data/checkpoints.db`), async SQLite |

Daha ayrıntılı adımlar: [QUICKSTART.md](QUICKSTART.md)

---

## Sorun giderme

| Sorun | Çözüm |
|-------|--------|
| `ModuleNotFoundError` / “Paketler eksik” | Proje kökünde: `pip install -e .` (veya `Run.ps1` / `./Run.sh`). Hâlâ olmazsa `.venv` sil → betiği `-ForceInstall` ile yeniden çalıştır |
| `ghost-attend … requires langchain-google-genai>=4.2` ama ortamda 2.x | Eski kurulum: `pip install -e .` ile projeyi yeniden kurun; gerekirse `.venv` silip betiği baştan çalıştırın |
| `thought_signature` / Gemini 400 (araç çağrısı sonrası) | `langchain-google-genai` 4.2+ kullanın. `GEMINI_MODEL=gemini-2.5-flash` en az sürtünme ile çalışır |
| `SqliteSaver does not support async` | Eski anlatım; projede `AsyncSqliteSaver` — bağımlılıkları güncel tutun |
| `python` / `pip` tanınmıyor | Windows: `Run.ps1` veya `GHOST_ATTEND_PYTHON` ile tam yol |
| Playwright tarayıcı yok | `python -m playwright install chromium` |
| Telegram / API hatası | `.env`: `TELEGRAM_BOT_TOKEN` ve `GOOGLE_API_KEY` dolu ve doğru mu |

---

## Güvenlik

`.env` asla commit edilmez ([`.gitignore`](.gitignore)). Token sızdıysa BotFather’dan yeni token alın.
