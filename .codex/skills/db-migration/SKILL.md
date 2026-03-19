---
name: db-migration
description: Use when modifying the database schema: adding tables, columns, indexes, or constraints. Triggers on: "add column", "new table", "migrate", "schema change", "alembic", "update model". Covers the full cycle: SQLAlchemy model update -> Alembic migration -> fixtures and tests update.
allow_implicit_invocation: true
---

## Context

The project uses PostgreSQL with async SQLAlchemy and Alembic. All timestamps are stored as UTC in
timezone-aware columns. Sensitive fields such as email and password are encrypted at the
application layer before persistence.

## Core Ownership Model

Use this data ownership model unless the architecture docs are explicitly updated:

```text
users
  - telegram_id
  - email_encrypted
  - password_encrypted
  - timezone
  - university_url

courses
  - user_id FK
  - name
  - day_of_week
  - start_time_utc
  - end_time_utc
  - teams_link

sessions
  - id (UUID)
  - user_id FK
  - is_active
  - created_at
  - closed_at
  - session_metadata

scheduler_jobs
  - id
  - user_id FK
  - course_id FK
  - job_type
  - apscheduler_job_id
  - is_active

human_input_requests
  - id
  - session_id FK
  - user_id FK
  - tool_name
  - reason
  - prompt
  - screenshot_path
  - status
  - expires_at

audit_events
  - id
  - user_id FK
  - session_id FK nullable
  - event_type
  - payload_json
  - created_at
```

`courses` belong to `user_id`, not `session_id`.

## Step-by-Step

### Step 1 - Update the SQLAlchemy models

Edit the declarative models, typically in `app/db/models.py`.

Rules:

- use `DateTime(timezone=True)` for timestamps
- use `UUID` for durable identifiers where appropriate
- index foreign keys and frequently filtered columns
- keep encrypted fields as ordinary string columns with encryption handled outside the model layer

### Step 2 - Generate the Alembic migration

```bash
alembic revision --autogenerate -m "short_description"
```

Then inspect the generated migration carefully. Do not trust autogeneration blindly.

### Step 3 - Verify upgrade and downgrade

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Every migration must be reversible unless there is a documented exceptional reason.

### Step 4 - Update fixtures and factories

Update `tests/conftest.py` and any model factories so the test suite reflects the new schema.

Particularly important:

- ownership changes between `user`, `course`, and `session`
- new audit or human-input tables
- new non-null constraints

### Step 5 - Update docs

If the schema change affects runtime behavior or ownership, update:

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `CHANGELOG.md`

## Rules

- never store plaintext credentials
- never persist browser cookies in the database
- do not put schedule ownership on `session_id`
- do not create schema that assumes browser session restore after restart
- model recovery as fresh runtime reconstruction plus re-login

## What To Watch For

- if adding a table used for operational recovery, define how it expires or is archived
- if adding a JSON payload column, document the producer and consumer
- if adding security-sensitive state, ensure audit coverage exists for changes to that state
