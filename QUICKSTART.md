# Quick start

This guide is step-by-step for **Windows**, **Linux/macOS**, and **Docker**. After each major step, use the **Verify** line to confirm you are on track.

---

## 0. Prerequisites

### Windows

- [ ] **Python 3.11+** installed from [python.org](https://www.python.org/downloads/) with **“Add python.exe to PATH”** checked.
- [ ] **PowerShell** available (default on Windows 11).
- [ ] *(Optional)* **Docker Desktop** if you choose the Docker path.

**Verify (PowerShell):**

```powershell
python --version
```

You should see `Python 3.11.x` or newer.

### Linux / macOS

- [ ] `python3` and `pip` available (3.11+).
- [ ] *(Optional)* **Docker Engine** + Compose if you choose the Docker path.

**Verify:**

```bash
python3 --version
```

---

## 1. Accounts and keys

You need:

| Item | Where |
|------|--------|
| Telegram bot token | [BotFather](https://t.me/BotFather) |
| Gemini API key | [Google AI Studio](https://aistudio.google.com/app/apikey) |

**Verify:** You have two opaque strings ready to paste into `.env` (never commit them).

---

## 2. Clone the repository

```bash
git clone https://github.com/xPoleStarx/GhostMyShit.git
cd GhostMyShit
```

SSH (optional):

```bash
git clone git@github.com:xPoleStarx/GhostMyShit.git
cd GhostMyShit
```

**Verify:** `ls` / `dir` shows `Run.ps1`, `Run.sh`, `pyproject.toml`, and `.env.example`.

---

## 3. Create `.env`

### Windows (PowerShell)

```powershell
Copy-Item .env.example .env
notepad .env
```

### Linux / macOS

```bash
cp .env.example .env
${EDITOR:-nano} .env
```

Set at minimum:

- `TELEGRAM_BOT_TOKEN=...`
- `GOOGLE_API_KEY=...`

Leave other keys as in `.env.example` unless you know you need to change them.

**Verify:** `.env` exists in the project root and is **not** tracked by git (`git status` should not list `.env` as a new file to commit if you only edited an ignored file—if unsure, check [`.gitignore`](.gitignore)).

---

## 4. Run the bot

Pick **one** path below.

### Windows (recommended)

```powershell
.\Run.ps1
```

Or double-click **`run.bat`**.

**What you should see:** virtualenv creation/updates, `pip install -e .`, Playwright Chromium install if needed, then the process stays running (polling Telegram).

**Verify:** No traceback at startup; logs indicate the bot is listening.

**If the script is blocked:**

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**If `python` is not found:**

```powershell
$env:GHOST_MYSHIT_PYTHON = "C:\Path\To\python.exe"
.\Run.ps1
```

**Faster iterations (only after a successful full run):**

```powershell
.\Run.ps1 -SkipInstall
```

**Force clean reinstall:**

```powershell
.\Run.ps1 -ForceInstall
```

**Install only (then run with skip):**

```powershell
.\Run.ps1 -InstallOnly
.\Run.ps1 -SkipInstall
```

### Linux / macOS

```bash
chmod +x Run.sh
./Run.sh
```

**Optional Python path:**

```bash
export GHOST_MYSHIT_PYTHON=/usr/bin/python3
./Run.sh
```

**Verify:** Same as Windows—process runs without immediate crash.

Flags mirror Windows:

| Goal | Flag |
|------|------|
| Install only | `--install-only` |
| Skip install | `--skip-install` |
| Force reinstall | `--force-install` |
| Non-interactive (no `.env` prompt) | `--non-interactive` |

### Docker (no Python on the host)

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose on Linux).
2. Ensure `.env` is filled at the **repository root** (same folder as `docker-compose.yml`).
3. Run:

```bash
docker compose up --build
```

**Verify:** Container stays up; `./data` on the host is mounted for checkpoint data (see [`docker-compose.yml`](docker-compose.yml)).

---

## 5. Confirm Telegram

1. Open your bot in Telegram (the username BotFather gave you).
2. Send a normal text message ( **`/start` is optional** ).

**Verify:** The bot responds or starts processing; for web tasks it may ask questions or send screenshots when HITL triggers.

**Useful commands** (see [`app/telegram/bot.py`](app/telegram/bot.py)):

| Command | Purpose |
|---------|---------|
| `/start` | Welcome + hints |
| `/tarayici` | Close browser-use session for this chat; next task gets a fresh browser |
| `/temizle` or `/reset` | Reset context for this chat |

---

## 6. Manual install (without Run scripts)

Use this when you prefer full control or CI.

```bash
cd GhostMyShit
python3 -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
python -m playwright install chromium
python -m app.main
```

**Alternative entry point** (from [`pyproject.toml`](pyproject.toml)):

```bash
GhostMyShit
```

**Verify:** Same Telegram checks as §5.

---

## 7. Development install

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

**Verify:** Tests run (async mode is configured in `pyproject.toml`).

---

## 8. Common issues (short)

| Symptom | Fix |
|---------|-----|
| Missing Python packages | `pip install -e .` from project root, or rerun `Run.ps1` / `Run.sh` |
| Old `langchain-google-genai` (2.x) in env | Remove `.venv`, rerun install; `pyproject.toml` requires `>=4.2` |
| Gemini `thought_signature` / 400 after tools | Stay on `langchain-google-genai>=4.2`; default `GEMINI_MODEL=gemini-2.5-flash` is the smoothest path |
| No Chromium | `python -m playwright install chromium` |
| More detail | Collapsible **Troubleshooting** in [README.md](README.md) |

---

## Maintainer

**Seyfullah Korkmaz** — [seyfullahkorkmaz115@gmail.com](mailto:seyfullahkorkmaz115@gmail.com)
