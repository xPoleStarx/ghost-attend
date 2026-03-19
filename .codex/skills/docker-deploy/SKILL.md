---
name: docker-deploy
description: Use when modifying Docker configuration, adding services, changing environment variables, or troubleshooting container issues. Triggers on: "docker", "docker-compose", "add service", "container", "env var", "deployment", "Oracle server", "production setup", "redis config". Covers the standardized Redis + Celery deployment model.
allow_implicit_invocation: true
---

## Context

The project is containerized end to end. The target runtime uses:

- `bot` service for Telegram and LangGraph orchestration
- `worker` service for Celery task execution
- `db` for PostgreSQL
- `redis` as Celery broker and utility store

RQ is not part of the deployment target.

## Services

| Service | Purpose |
|---|---|
| `bot` | Main application process |
| `worker` | Celery workers for browser and automation tasks |
| `db` | PostgreSQL durable storage |
| `redis` | Celery broker and lightweight coordination store |

## Timezone Rules

Container time stays in UTC.

```yaml
services:
  bot:
    environment:
      - TZ=UTC
  worker:
    environment:
      - TZ=UTC
  db:
    environment:
      - TZ=UTC
```

User-local rendering belongs in the application layer, not container config.

## Environment Variable Changes

When adding a new env var:

1. add it to `docker-compose.yml`
2. add it to `.env.example`
3. add it to the application settings model
4. update `README.md` if it is user- or operator-facing

Do not hide deployment-critical configuration in code defaults alone.

## Browser Runtime in Docker

The browser layer uses a shared Chromium process with per-user contexts.

Operational implication:

- browser contexts are ephemeral
- restart destroys all contexts
- restart recovery must recreate contexts and re-login if needed

Do not document or implement restart as cookie-based browser session restore.

## Worker and Scheduling Model

- APScheduler decides when work should happen
- scheduled jobs enqueue Celery tasks
- Celery executes the actual login, join, leave, screenshot, and recovery workflows

This separation should be reflected in compose commands and operator docs.

## Health Checks

Every service should have a health check.

Examples:

- `bot`: import app settings or run a lightweight application probe
- `worker`: validate Celery worker process readiness
- `db`: use `pg_isready`
- `redis`: use `redis-cli ping`

## Production Expectations

Minimum production expectations:

- `restart: unless-stopped`
- named volume for PostgreSQL data
- no host-mounted secret files by default
- explicit worker concurrency
- logs available for both `bot` and `worker`

## Operational Concerns

Plan for:

- queue backlog visibility
- failed task inspection
- browser memory pressure
- restart recovery behavior
- secret injection from the deployment platform or secret manager

## What Not To Do

- do not reintroduce RQ or ambiguous queue wording
- do not set container timezone to a local timezone
- do not claim browser sessions survive restart
- do not add deployment behavior that bypasses documented security rules
