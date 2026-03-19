# DYS Attendance Agent - Codex Instructions

## Project Overview

An autonomous Telegram-based attendance agent for Turkish university students. The system logs into
the university portal (DYS), navigates Microsoft Teams Web through browser automation, and joins
online lectures on the student's behalf. Interaction with the student happens through Telegram, and
human intervention is requested only for blocking situations such as 2FA or explicit confirmation.

Primary goals:

- zero manual attendance effort for the student
- high reliability under multi-tenant usage
- predictable recovery behavior after failures or restarts
- clean architecture that can be expanded in phases without rework

## Technology Standards

| Layer | Standard |
|---|---|
| Language | Python 3.11+ |
| Telegram | `python-telegram-bot` async |
| Agent orchestration | LangGraph |
| Browser automation | Browser-use plus Playwright |
| Scheduler | APScheduler |
| Queue | Redis + Celery |
| Database | PostgreSQL with async SQLAlchemy |
| Migrations | Alembic |
| Container | Docker + Docker Compose |
| CI | GitHub Actions |
| Testing | `pytest`, `pytest-asyncio` |

Queue choice is fixed. Do not introduce RQ into the target architecture.

## Architecture

```text
Telegram Bot
    |
    v
LangGraph StateGraph <-> PostgreSQL
    |                     |
    |                     +-> users
    |                     +-> courses
    |                     +-> sessions
    |                     +-> scheduler_jobs
    |                     +-> human_input_requests
    |                     +-> audit_events
    |
    +-> APScheduler -> Celery -> browser and agent tasks
    |
    +-> Tool handlers
           |
           v
   Browser-use + Playwright
           |
           v
   Shared Chromium -> per-user BrowserContext
```

## Browser Responsibilities

Use both Browser-use and Playwright, but keep their responsibilities separate.

### Browser-use

- semantic navigation through DYS and Teams
- UI exploration where structure may vary by university
- task-level automation phrased as goals

### Playwright

- browser launch and shutdown
- browser context lifecycle
- permission grants for mic and camera
- tabs, screenshots, waits, network-idle guards, deterministic recovery probes

Never use hardcoded selectors as the main automation strategy. Use Playwright primitives only when
the action is deterministic and low-level.

## Session Lifecycle

1. User sends `/start`
2. Bot collects university DYS URL, email, password, timezone, and schedule input
3. Schedule input is parsed into a candidate structure
4. Bot asks the user to confirm or correct the parsed schedule
5. After confirmation, durable user data and courses are stored
6. A new `session_id` is created and used as the LangGraph thread key
7. Subsequent messages go directly to the agent
8. User sends `/quit`
9. Session is marked inactive, browser context is destroyed, thread memory is cleared
10. Durable data remains in the database for future sessions

No schedule should become active before explicit confirmation.

## Data Ownership Model

### Durable data

- `users`: Telegram identity, encrypted credentials, timezone, university URL
- `courses`: schedule entries owned by `user_id`
- `scheduler_jobs`: materialized jobs derived from user courses

### Runtime data

- `sessions`: one active conversational and automation runtime
- `human_input_requests`: pauses waiting for user action
- `audit_events`: immutable lifecycle and security history

`courses` must belong to `user_id`, not `session_id`.

## LangGraph Agent Design

The agent uses a single router node that classifies incoming messages into:

- `CHAT`
- `TOOL_CALL`
- `CLARIFY`

The full confirmed schedule is injected into the system prompt at session start. Tool selection is
semantic rather than regex-based.

### State Schema

`AgentState` should include at least:

- `session_id`
- `user_id`
- `user_timezone`
- `schedule`
- `awaiting_human_input`
- `pending_tool`
- `pending_human_input_request_id`
- `meeting_state`
- `last_screenshot_path`

### Human input pause pattern

When a tool requires user input:

1. create a `human_input_requests` record with correlation data
2. mark `awaiting_human_input = true`
3. store `pending_tool` and `pending_human_input_request_id`
4. send Telegram prompt and optional screenshot
5. route the next user reply to the resume node
6. resolve or expire the request explicitly

## Tool Contract

Every tool must:

- accept one typed Pydantic v2 input model
- return `ToolResult(success: bool, message: str, screenshot_path: str | None)`
- wrap failures in `try/except`
- enforce `MAX_TOOL_TIMEOUT` through `asyncio.wait_for`
- log start and finish with `structlog`
- avoid leaking exceptions to the agent loop

Retries are allowed only for recoverable failures. Auth failures and ambiguous actions must not be
retried silently.

## Dependency Injection Standard

Do not import shared services as globals.

Startup must construct an application container, for example:

```python
container = AppContainer(...)
tools = build_tools(container)
graph = build_graph(container=container, tools=tools)
```

Preferred tool pattern:

- callable class with constructor-injected services

Alternative allowed pattern:

- factory function returning a closure with bound dependencies

## Core Tools

### Authentication

- `login_to_dys(email, password)`
  - creates or reuses an active browser context
  - logs into DYS
  - detects 2FA and pauses through `request_human_input`
  - stores the resulting authenticated state only in the live browser context

### Schedule management

- `add_course(name, day, start_time, end_time, teams_link)`
- `remove_course(course_id_or_name)`
- `update_course(course_id_or_name, fields...)`

These update durable course records and regenerate scheduler jobs.

### Class actions

- `join_teams_meeting(course_id)`
- `leave_meeting()`
- `take_screenshot()`
- `read_teams_chat()`

### Human-in-the-loop

- `request_human_input(prompt, context_screenshot)`

This is a workflow tool that must create a durable request record and correlate the reply back into
the paused flow.

## Meeting State Model

Meeting runtime must be explicit:

- `IDLE`
- `PREPARING`
- `LOGGING_IN`
- `JOINING`
- `WAITING_ROOM`
- `IN_MEETING`
- `LEAVING`
- `PAUSED_HUMAN_INPUT`
- `ERROR`

Required decisions:

- if already in a meeting, do not launch a second meeting
- if two courses overlap, apply a documented conflict policy
- if the meeting ends unexpectedly, notify the user and write an audit event
- if the meeting is not started yet, remain in `WAITING_ROOM` with bounded polling

## Edge Cases

### Authentication

- 2FA: pause and request human input
- wrong password: stop after one attempt and notify the user
- redirect loops: bounded timeout
- repeated login failures: apply cooldown and emit audit event

### Class join

- ambiguous course match: ask naturally, do not guess
- waiting room: poll with user-visible status updates
- permission popups: pre-grant in browser context options
- page load timeout: capture screenshot, then request human input if needed

### Screenshots

- no active session: return a graceful message
- blank page: wait for `networkidle`, retry once

### Recovery

- restart destroys all browser contexts
- recovery means creating a fresh context and re-running login if needed
- if re-login hits 2FA, pause and request user input

## Time and Timezone Rules

Golden rule: store in UTC, display in the user's local timezone.

- Docker timezone stays `UTC`
- PostgreSQL timestamps use timezone-aware columns
- onboarding captures or infers `user.timezone`
- APScheduler runs in UTC
- user-facing times are rendered in the stored user timezone

## Multi-Tenant Concurrency

- one shared Chromium binary per container
- one isolated `BrowserContext` per active user session
- contexts are created on demand
- contexts are destroyed on `/quit`, after meeting completion, or during failure cleanup
- Celery workers execute tool and join flows
- worker concurrency must be tuned conservatively against memory usage

## Observability and Auditability

Baseline requirements:

- structured logs with correlation IDs
- audit events for auth, session, schedule, and meeting lifecycle
- Celery task status visibility
- metrics for login success, join success, recovery count, waiting-room duration, and human-input pauses
- health checks for bot, worker, db, and redis

## Security Rules

- never commit secrets
- never persist session cookies
- never log decrypted credentials
- screenshots should be retained only as long as operationally necessary
- plan for future key rotation and re-encryption migration

## CI and Delivery

Every push or PR should run:

- `ruff`
- `mypy`
- `pytest`
- Docker build check

The project should be delivered in phases, not as one large implementation burst. See
`docs/ROADMAP.md` for the milestone order and exit criteria.

## Repository Consistency Rules

Keep these files aligned whenever behavior changes:

- `README.md`
- `CHANGELOG.md`
- `.env.example`
- `pyproject.toml`
- `docker-compose.yml`
- `SECURITY.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
