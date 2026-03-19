# ghost-attend

A **Telegram** bot that runs web tasks with **LangGraph** + **browser-use** (Playwright) + **Google Gemini**. It pauses on login / sensitive steps, sends screenshots and questions, and continues with your reply (HITL).

**Fast path:** clone the repo → fill `.env` → `.\Run.ps1` (Windows) or `./Run.sh` (Linux/macOS). Details in the tables below.

---

## After cloning (summary)

| Step | What to do |
|------|------------|
| 1 | Clone: `git clone …` and `cd` into the folder |
| 2 | Install **Python 3.11+** ([python.org](https://www.python.org/downloads/)); on Windows, check **“Add python.exe to PATH”** |
| 3 | Prepare **`.env`**: copy `.env.example` → `.env`, set `TELEGRAM_BOT_TOKEN` and `GOOGLE_API_KEY` |
| 4 | Run one of the **single-command** scripts: venv → `pip install -e .` (deps from [`pyproject.toml`](pyproject.toml)) → Playwright Chromium → import check → bot |

**Dependencies:** single source of truth is [`pyproject.toml`](pyproject.toml). [`requirements.txt`](requirements.txt) is only for manual `pip install -r` compatibility; `Run.ps1` / `Run.sh` **no longer** read `requirements.txt` first (avoids accidentally pinning `langchain-google-genai` to 2.x).

---

## Automated setup + run (recommended)

### Windows

PowerShell or `run.bat`:

```powershell
cd ghost-attend
.\Run.ps1
```

Double-click: **`run.bat`**

Each run (without `-SkipInstall`): idempotent `pip install` → Playwright → import check for **`app.main` + `app.agent.task_agent`** → copy `.env` from example if missing → bot.

- Quick start (skip install): `.\Run.ps1 -SkipInstall` — only if venv and packages are already OK.
- Force reinstall all packages: `.\Run.ps1 -ForceInstall`
- Install only: `.\Run.ps1 -InstallOnly` — then `.\Run.ps1 -SkipInstall`
- Script blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
- Python not found: `$env:GHOST_ATTEND_PYTHON = "C:\...\python.exe"` then `.\Run.ps1`

### Linux / macOS

```bash
cd ghost-attend
chmod +x Run.sh
./Run.sh
```

Optional: `export GHOST_ATTEND_PYTHON=/usr/bin/python3`

Same flow: venv, `pip install -e .`, Playwright, `.env`, bot.

### Docker (no Python on the host)

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/); ensure `.env` is filled at the project root.

```bash
docker compose up --build
```

---

## Manual setup (IDE / CI / fine-tuning)

```bash
cd ghost-attend
python3 -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
# Optional two-step: pip install -r requirements.txt && pip install -e .
python -m playwright install chromium
copy .env.example .env   # or cp; edit .env
python -m app.main
# Alternative (pyproject script): ghost-attend
```

Dev (tests): `python -m pip install -e ".[dev]"`

Verify: `python -m pip check` · `python -m pytest` (if tests exist)

---

## Makefile (Linux / macOS, if `make` is available)

```bash
make install    # venv + requirements + editable + playwright + .env template
make run        # bot
make test       # pytest
```

---

## Environment variables (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | BotFather token |
| `GOOGLE_API_KEY` | Yes | Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `GEMINI_MODEL` | No | Default: `gemini-2.5-flash`. For Gemini 3.x you need `langchain-google-genai>=4.2` (declared in this project); otherwise you may see `thought_signature` errors after tool calls. |
| `PLAYWRIGHT_HEADLESS` | No | `false` = visible browser (local); usually `true` in Docker |
| `CHECKPOINT_PATH` | No | LangGraph: SQLite file (`AsyncSqliteSaver`), default `./data/checkpoints.db` |
| `BROWSER_MAX_STEPS` | No | browser-use step limit (default `35`) |
| `BROWSER_STEP_TIMEOUT` | No | Per-step timeout in seconds (default `180`) |

Template: [`.env.example`](.env.example)

---

## Using Telegram

| What | Description |
|------|-------------|
| **First message** | Open the bot in Telegram and type; `/start` is **not** required. Your first message is handled by LangGraph + Gemini. |
| `/start` | Sends a short welcome + `/tarayici` hint (recommended to remember commands). |
| `/tarayici` | Closes the **browser-use** session for this chat; the next web task opens a new Chromium window. |

Commands are registered with `CommandHandler` in [`app/telegram/bot.py`](app/telegram/bot.py).

---

## Architecture (short)

| Piece | Location |
|-------|----------|
| Gemini task agent (ReAct, tools) | `app/agent/task_agent.py`, `app/agent/tools.py` |
| Tools | `run_browser_automation`, `capture_page_screenshot`, `ask_user` (LangGraph `create_react_agent`) |
| browser-use (embedded browser) | `app/adapters/browser_use_runner.py` |
| Telegram | `app/telegram/` |
| Checkpoint | `app/persistence/checkpointer.py` — `CHECKPOINT_PATH` (default `./data/checkpoints.db`), async SQLite |

More detail: [QUICKSTART.md](QUICKSTART.md)

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError` / “missing packages” | From project root: `pip install -e .` (or `Run.ps1` / `./Run.sh`). If it persists, delete `.venv` and rerun with `-ForceInstall` |
| `ghost-attend … requires langchain-google-genai>=4.2` but env has 2.x | Old install: reinstall with `pip install -e .`; if needed, remove `.venv` and run the script from scratch |
| `thought_signature` / Gemini 400 (after tool calls) | Use `langchain-google-genai` 4.2+. `GEMINI_MODEL=gemini-2.5-flash` is the smoothest path |
| `SqliteSaver does not support async` | Outdated docs; this project uses `AsyncSqliteSaver` — keep dependencies current |
| `python` / `pip` not found | Windows: `Run.ps1` or set `GHOST_ATTEND_PYTHON` to full path |
| No Playwright browser | `python -m playwright install chromium` |
| Telegram / API errors | Check `.env`: `TELEGRAM_BOT_TOKEN` and `GOOGLE_API_KEY` are set and correct |

---

## Security

Never commit `.env` ([`.gitignore`](.gitignore)). If a token leaks, rotate it in BotFather.
