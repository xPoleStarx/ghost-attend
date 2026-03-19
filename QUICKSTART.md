# Hızlı başlangıç

## Gereken hesaplar / anahtarlar

- [Telegram BotFather](https://t.me/BotFather) → bot token  
- [Google AI Studio](https://aistudio.google.com/app/apikey) → `GOOGLE_API_KEY`

## 1. Repoyu indir

```bash
git clone <bu-reponun-git-url-i>
cd ghost-attend
```

## 2. Ortam dosyası

```bash
cp .env.example .env
# Windows: Copy-Item .env.example .env
```

`.env` içinde en az: `TELEGRAM_BOT_TOKEN`, `GOOGLE_API_KEY`.

## 3. Tek komutla kur + çalıştır

### Windows

```powershell
.\Run.ps1
```

veya `run.bat` (çift tık).

### Linux / macOS

```bash
chmod +x Run.sh
./Run.sh
```

### Docker

```bash
docker compose up --build
```

## 4. Manuel (betik kullanmadan)

**Python 3.11+** ve `pip` gerekir.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip setuptools wheel
pip install -e .
# veya: pip install -r requirements.txt && pip install -e .
python -m playwright install chromium
python -m app.main
```

`requirements.txt` ile `pyproject.toml` aynı sürüm aralıklarını taşır; tek satır `pip install -e .` yeterlidir.

Geliştirici araçları: `pip install -e ".[dev]"`

## Betik parametreleri (Run.ps1 / Run.sh)

| Parametre | Windows | Linux/macOS |
|-----------|---------|-------------|
| Sadece kurulum | `-InstallOnly` | `--install-only` |
| Kurulum atla | `-SkipInstall` | `--skip-install` |
| Bağımlılığı yeniden kur | `-ForceInstall` | `--force-install` |
| `.env` bekletmeden devam | `-NonInteractive` | `--non-interactive` |

## Python bulunamıyor (Windows)

```powershell
$env:GHOST_ATTEND_PYTHON = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
.\Run.ps1
```

## PowerShell betiği engelleniyor

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
