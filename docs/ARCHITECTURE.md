# Architecture Clarifications

This document resolves the design ambiguities that existed between the quickstart docs and the internal project instructions. If this file and another markdown disagree, this file and `AGENTS.md` are the source of truth.

## Decision Summary

### Queue and Background Execution

- The project standard is **Redis + Celery**
- Redis is used as the Celery broker and lightweight pub/sub utility store
- RQ is not part of the target architecture
- APScheduler remains responsible for time-based scheduling decisions
- Scheduled jobs enqueue Celery tasks; Celery workers execute browser and agent work

Why this choice:

- stronger retry controls
- better task routing and visibility
- cleaner path to production hardening than RQ

## Browser Control Boundary

The system intentionally uses both Browser-use and Playwright, but with different responsibilities.

### Browser-use responsibilities

- semantic navigation inside DYS and Teams
- task-level browser automation driven by natural-language goals
- handling UI flows where the exact structure may vary across universities

### Playwright responsibilities

- launching and closing the shared browser
- creating and destroying per-user `BrowserContext` instances
- granting mic/camera permissions
- opening or closing tabs deterministically
- screenshots, file downloads, page wait conditions, and low-level recovery checks

### Rule of thumb

Use Browser-use for "figure out how to get there." Use Playwright for "perform this exact browser primitive safely."

## Session, Cookies, and Restart Semantics

- Cookies live only inside the in-memory browser context
- Cookies are never serialized to disk, Redis, or PostgreSQL
- A container restart destroys all browser contexts
- Therefore, the system does **not** restore browser sessions after restart
- Instead, it performs **session recovery**

### Session recovery

When the app restarts:

1. query the database for sessions marked `is_active = true`
2. recreate the user runtime state in memory
3. build a fresh browser context on demand
4. re-run `login_to_dys` using encrypted credentials if the user has an active schedule window or a pending job
5. if 2FA is required, pause and request human input

This is a recovery flow, not a browser-context restore flow.

## Ownership Model

The durable ownership model is:

- `users`: identity, credentials, timezone, university URL
- `courses`: durable schedule owned by `user_id`
- `sessions`: runtime chat and automation lifetime for one active run
- `scheduler_jobs`: materialized execution plan for a user's courses
- `human_input_requests`: correlation records for paused flows
- `audit_events`: immutable operational history

`courses` belong to the user because schedule data must survive `/quit` and future sessions.

## Onboarding and Schedule Ingestion

Schedule ingestion is a two-step pipeline.

### Step 1: extraction

The bot accepts either:

- structured text
- a schedule screenshot or PDF image

The parser produces a candidate structure:

```json
{
  "courses": [
    {
      "name": "Kariyer Planlama",
      "day_of_week": "MONDAY",
      "start_local": "14:00",
      "end_local": "15:45",
      "teams_link": null,
      "confidence": 0.93,
      "source_fragment": "..."
    }
  ],
  "warnings": [],
  "needs_confirmation": true
}
```

### Step 2: confirmation

The parsed schedule is shown back to the user in plain language.

- low-confidence items are highlighted
- missing links or times are called out explicitly
- the user must confirm or correct the candidate schedule before activation

No schedule becomes active until the confirmation step succeeds.

## Tool Dependency Injection

Tools must not import application services as globals. The project standard is:

- create an `AppContainer` at startup
- construct service instances once
- build tool handlers from that container

Recommended shape:

```python
container = AppContainer(...)
tools = build_tools(container)
graph = build_graph(tools=tools, container=container)
```

Each tool handler may be:

- a small callable class with injected services, or
- a closure returned by a factory

The preferred pattern is a callable class because it is easier to test, introspect, and extend.

## Human Input Contract

`request_human_input` is a first-class workflow, not an ad hoc Telegram message.

Each pause creates a `human_input_requests` record with:

- `id` or correlation ID
- `session_id`
- `user_id`
- `tool_name`
- `reason`
- `prompt`
- `screenshot_path`
- `status`
- `expires_at`

### Flow

1. tool detects blocking state
2. tool creates a `human_input_requests` record
3. bot sends the prompt and optional screenshot to Telegram
4. agent marks state as `awaiting_human_input = true`
5. next user reply is matched to the open request by `session_id` and pending request status
6. resume node injects the reply into the pending tool flow
7. request is marked `resolved` or `expired`

### Timeout policy

- 2FA or meeting join prompts expire after a configurable timeout
- expired requests produce a terminal tool result with a clear explanation
- retries must be explicit, not silent

## Meeting Runtime State

Meeting control uses an explicit state model:

- `IDLE`
- `PREPARING`
- `LOGGING_IN`
- `JOINING`
- `WAITING_ROOM`
- `IN_MEETING`
- `LEAVING`
- `PAUSED_HUMAN_INPUT`
- `ERROR`

### Required behaviors

- if already `IN_MEETING`, a second join request returns the current meeting status instead of opening a second meeting
- if two courses overlap, the scheduler must apply a conflict policy instead of guessing
- if the meeting ends unexpectedly, the session records an audit event and notifies the user
- if the meeting never starts, the system remains in `WAITING_ROOM` with bounded polling and user-visible status updates

## Rate Limiting and Abuse Controls

The bot must protect both the infrastructure and the student account.

Minimum required controls:

- one active session per user
- deduplicate repeated `/start` and join requests within a short window
- per-user Telegram command rate limiting
- bounded retries for login and join flows
- repeated auth failures trigger a cooldown and explicit user notification

## Observability Standard

The production baseline includes:

- structured logs with request, session, course, and task correlation IDs
- audit trail records for security-sensitive and lifecycle events
- task-level status visibility for Celery jobs
- basic metrics for login attempts, join success rate, recovery count, waiting-room duration, and human-input pauses
- health checks for bot, worker, db, and redis

Alerting can be added later, but the data needed for alerting must exist from the start.
