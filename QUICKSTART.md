# Quick start

## Accounts / keys you need

- [Telegram BotFather](https://t.me/BotFather) → bot token  
- [Google AI Studio](https://aistudio.google.com/app/apikey) → `GOOGLE_API_KEY`

## 1. Clone the repo

```bash
git clone <this-repo-git-url>
cd GhostMyShit
```

## 2. Environment file

```bash
cp .env.example .env
# Windows: Copy-Item .env.example .env
```

In `.env` at minimum: `TELEGRAM_BOT_TOKEN`, `GOOGLE_API_KEY`.

## 3. One-command install + run

### Windows

```powershell
.\Run.ps1
```

Or `run.bat` (double-click).

### Linux / macOS

```bash
chmod +x Run.sh
./Run.sh
```

### Docker

```bash
docker compose up --build
```

## 4. Manual (without the scripts)

You need **Python 3.11+** and `pip`.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip setuptools wheel
pip install -e .
# or: pip install -r requirements.txt && pip install -e .
python -m playwright install chromium
python -m app.main
```

`requirements.txt` mirrors version ranges from `pyproject.toml`; a single `pip install -e .` is enough.

Dev dependencies: `pip install -e ".[dev]"`

## Script flags (Run.ps1 / Run.sh)

| Flag | Windows | Linux/macOS |
|------|---------|-------------|
| Install only | `-InstallOnly` | `--install-only` |
| Skip install | `-SkipInstall` | `--skip-install` |
| Force reinstall | `-ForceInstall` | `--force-install` |
| Non-interactive (no `.env` prompt) | `-NonInteractive` | `--non-interactive` |

## Python not found (Windows)

```powershell
$env:GHOST_MYSHIT_PYTHON = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
.\Run.ps1
```

## PowerShell script is blocked

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

---

## Author & contact

This project is developed by **Seyfullah Korkmaz**. For questions or feedback, email [seyfullahkorkmaz115@gmail.com](mailto:seyfullahkorkmaz115@gmail.com).
