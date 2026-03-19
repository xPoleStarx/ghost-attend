# Ghost Attend

> A Telegram-first attendance agent for DYS-based university courses that logs in, joins Teams classes, and keeps the student in the loop only when needed.

[![CI](https://github.com/YOUR_USERNAME/ghost-attend/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/ghost-attend/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## What It Does

- Guides the student through LLM-managed onboarding in Telegram from the very first `/start`
- Reads schedule screenshots with the configured multimodal LLM and converts them into structured course lines
- Stores credentials securely and uses them to log into the university DYS portal
- Opens the course's Microsoft Teams meeting in an isolated browser context
- Sends proactive notifications before class
- Requests human input only for genuinely blocking situations such as 2FA or ambiguous confirmations
- Supports many concurrent students with per-user isolation

## Product Boundaries

- First-class support is limited to universities whose DYS flow has been validated by tests or manual verification
- Other DYS-based universities are treated as experimental until their login and meeting flows are verified
- Cookies are kept in memory only; after a container restart, the system performs session recovery by creating a fresh browser context and re-running login when policy allows

## Core Technical Decisions

- Queue standard: Redis + Celery
- Orchestration: LangGraph with one thread per `session_id`
- Browser control split:
  - Browser-use handles semantic navigation and intent-level browser tasks
  - Playwright handles deterministic browser primitives such as context lifecycle, permissions, screenshots, tab management, and waiting for page state
- Persistence model:
  - `users` hold durable profile and schedule ownership
  - `sessions` hold runtime conversation and browser lifecycle state
  - `courses` belong to the user, not the session

## Quickstart

### Prerequisites

- Docker and Docker Compose
- For real Telegram usage: a bot token from [@BotFather](https://t.me/BotFather)
- For real LLM-driven browser flows: at least one supported LLM provider key

### Fastest Start

This repository can be booted even before you configure Telegram or LLM keys.

```bash
git clone https://github.com/xPoleStarx/ghost-attend
cd ghost-attend
docker compose up -d --build
```

What happens in this mode:

- PostgreSQL and Redis start
- the app waits for the database
- migrations are applied automatically
- the bot container stays alive in standby mode if `TELEGRAM_BOT_TOKEN` is missing

This is the easiest smoke test to confirm the stack boots correctly.

### Real Setup

```bash
git clone https://github.com/xPoleStarx/ghost-attend
cd ghost-attend
cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN and one LLM key
docker compose up -d --build
```

Then open Telegram, find your bot, and send `/start`.

### One-Command Env Creation

Windows PowerShell:

```powershell
.\scripts\setup.ps1
```

macOS / Linux:

```bash
sh ./scripts/setup.sh
```

These scripts create `.env` from `.env.example` if it does not exist.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | Telegram bot token from @BotFather |
| `LLM_PROVIDER` | yes | `gemini`, `openai`, or `anthropic` |
| `LLM_MODEL` | yes | Provider-specific model name |
| `GOOGLE_API_KEY` | if gemini | Google AI Studio API key |
| `OPENAI_API_KEY` | if openai | OpenAI API key |
| `ANTHROPIC_API_KEY` | if anthropic | Anthropic API key |
| `DATABASE_URL` | yes | PostgreSQL connection string |
| `REDIS_URL` | yes | Redis broker/result backend URL |
| `SECRET_KEY` | yes | 32-byte hex string used for credential encryption |
| `BROWSER_HEADLESS` | yes | `true` in production, `false` for local debugging |
| `PLAYWRIGHT_EXECUTABLE_PATH` | no | Optional explicit Chromium/Chrome executable path |
| `PAGE_TIMEOUT` | yes | Per-page timeout in milliseconds |
| `MAX_RETRIES` | yes | Retry count for recoverable tool failures |
| `WORKER_CONCURRENCY` | yes | Celery worker concurrency |
| `DEFAULT_TIMEZONE` | no | Fallback timezone, default `Europe/Istanbul` |

See `.env.example` for the current reference values.

### What You Do Not Need To Do Manually

- You do not need to run Alembic manually for the default Docker path
- You do not need to install Python locally if you are using Docker only
- You do not need to create PostgreSQL or Redis manually if you use `docker compose`

## Documentation Map

- [AGENTS.md](AGENTS.md): authoritative internal architecture and implementation rules
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): clarified system contracts and operating model
- [docs/ROADMAP.md](docs/ROADMAP.md): phased delivery plan and milestone exit criteria
- [CONTRIBUTING.md](CONTRIBUTING.md): development workflow
- [SECURITY.md](SECURITY.md): security model and vulnerability reporting

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy .
```

## Current Maturity

This repository is being built in deliberate phases. The current standard is not "ship the MVP as fast as possible" but "establish clean contracts, then implement in slices without compromising future maintainability."

See [docs/ROADMAP.md](docs/ROADMAP.md) for the phase plan.

## Security

Credentials are encrypted before storage, browser sessions are isolated per user, and session cookies are never persisted to disk or the database. See [SECURITY.md](SECURITY.md) for the full policy.

## License

MIT, see [LICENSE](LICENSE).
