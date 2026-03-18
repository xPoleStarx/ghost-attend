# GhostAttend

GhostAttend is a self-hosted automation system that joins university live classes on behalf of the user through a Telegram bot, a scheduler, and a browser automation worker.

It is designed for deployments where the user controls the infrastructure, stores credentials locally, and wants visibility into every important step of the automation lifecycle.

## Overview

GhostAttend combines four main capabilities:

- Telegram-based onboarding and control
- schedule ingestion from image or text
- scheduled execution through APScheduler and Celery
- browser automation through Playwright and `browser-use`

In practice, the system can:

- collect and securely store DYS / university portal credentials
- parse course schedules from screenshots or text input
- create recurring jobs before each lesson
- log into the university system
- locate the live class link
- join the class with camera and microphone disabled
- send progress updates and screenshots back to Telegram

## Architecture

At a high level the runtime looks like this:

```text
Telegram Bot <-> Redis <-> Celery Worker <-> Playwright / browser-use
      |              |             |
      v              v             v
  PostgreSQL     APScheduler     LLM-backed agent flow
```

Core services:

- `bot`: Telegram interaction layer
- `worker`: task execution and browser automation
- `scheduler`: recurring job orchestration
- `postgres`: persistent application state
- `redis`: queue, state, and scheduler persistence

Detailed architecture notes live in [architecture.md](architecture.md).

## Quick Start

The recommended flow is:

1. clone the repository
2. run the platform-specific setup script once
3. use the `dev` helper script for daily operations

### Windows

```powershell
git clone https://github.com/xPoleStarx/ghost-attend.git
cd ghost-attend
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

### Linux / macOS

```bash
git clone https://github.com/xPoleStarx/ghost-attend.git
cd ghost-attend
bash scripts/setup.sh
```

## What the Setup Script Does

The setup scripts are intended to reduce manual configuration to a minimum. They:

- create `.env` from `.env.example` if needed
- ask for the Telegram bot token
- ask for one LLM provider API key
- generate `MASTER_ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD`
- synchronize `DATABASE_URL` and `REDIS_URL` with the generated credentials
- start the development stack with a build

Authoritative setup details are documented in [docs/SETUP.md](docs/SETUP.md).

## Daily Operations

After the first installation, you should not need to remember raw `docker compose` commands.

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 up
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 rebuild
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 logs
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 ps
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 migrate
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 down
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 reset
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

## Logs and Diagnostics

To stream service logs from the terminal:

### Development stack

```powershell
docker compose -f docker-compose.dev.yml logs -f bot worker scheduler
```

### Production stack

```powershell
docker compose -f docker-compose.yml logs -f bot worker scheduler
```

If you want logs for a single container:

```powershell
docker logs -f ghost-attend-worker-1
docker logs -f ghost-attend-bot-1
docker logs -f ghost-attend-scheduler-1
```

Equivalent shorthand via the helper script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 logs
```

```bash
./scripts/dev.sh logs
```

## Development Workflow

Not every change requires the same action.

### When restart is usually enough

If you only changed Python files under `src/` while using `docker-compose.dev.yml`, the source code is mounted into the containers. In that case, restarting the relevant service is often enough.

### When rebuild is required

Use `rebuild` if you changed:

- `docker-compose*.yml`
- any `Dockerfile`
- environment variables
- Python dependencies
- Playwright installation behavior
- startup scripts

If you are unsure, `rebuild` is the safest option.

Recommended command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 rebuild
```

or:

```bash
./scripts/dev.sh rebuild
```

### Database changes

If a schema change is involved, also run migration:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 migrate
```

or:

```bash
./scripts/dev.sh migrate
```

## Environment Notes

Important runtime notes:

- development uses [`docker-compose.dev.yml`](docker-compose.dev.yml)
- production uses [`docker-compose.yml`](docker-compose.yml)
- worker and scheduler are forced into headless browser mode in containers
- the bot can still keep a developer-friendly `.env`, but containerized worker execution remains headless by design

## Security Model

This project is designed around self-hosting and local control:

- credentials are stored locally
- encryption is used for credential persistence
- browser execution happens inside your own infrastructure
- progress is surfaced through Telegram notifications and screenshots

See [docs/SECURITY.md](docs/SECURITY.md) for the security document.

## Documentation Index

- [Setup Guide](docs/SETUP.md)
- [Trigger Smoke Test](docs/TRIGGER_TEST.md)
- [Security](docs/SECURITY.md)
- [Contributing](docs/CONTRIBUTING.md)
- [Scenario Matrix](docs/SCENARIOS.md)
- [Architecture](architecture.md)

## Project Governance

- Contributions are documented in [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)
- Security expectations and disclosure guidance are documented in [docs/SECURITY.md](docs/SECURITY.md)
- Licensing terms are defined in [LICENSE](LICENSE)

## Disclaimer

This repository is intended for educational and self-hosted automation use. Compatibility with university systems, institutional rules, and platform terms remains the responsibility of the deployer.

## License

MIT
