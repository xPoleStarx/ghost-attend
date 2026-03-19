# Delivery Roadmap

The project will be built in deliberate phases. Each phase has exit criteria. Work should not jump ahead until the current phase is stable.

## Phase 0: Foundation and Contracts

Goal: establish the rules the codebase will follow.

Scope:

- application package layout
- settings and dependency injection foundation
- structured logging baseline
- database schema draft
- architecture, security, and delivery docs aligned

Exit criteria:

- all core markdown docs agree on queue, session, cookie, and ownership rules
- initial SQLAlchemy models and migration strategy are documented
- no unresolved contradiction remains in the architecture docs

## Phase 1: Durable Data and Security Core

Goal: make user, course, session, and audit data safe and testable.

Scope:

- `users`, `courses`, `sessions`, `scheduler_jobs`, `human_input_requests`, `audit_events`
- AES-256 credential encryption and decryption helpers
- repository layer
- migration tooling

Exit criteria:

- durable schedule belongs to `user_id`
- encrypted secrets are never logged
- migration up/down cycle is tested
- unit tests cover security and repository behavior

## Phase 2: Telegram Onboarding and Schedule Confirmation

Goal: safely collect the information needed to automate class attendance.

Scope:

- `/start` onboarding
- timezone capture
- text schedule ingestion
- image schedule parsing pipeline
- explicit user confirmation before schedule activation

Exit criteria:

- onboarding produces a valid `user` and `session`
- schedule confirmation works for both text and image-derived input
- low-confidence parsing paths are user-visible
- no schedule becomes active without confirmation

## Phase 3: Agent Core and Human-in-the-Loop Control

Goal: make the conversational runtime safe and resumable.

Scope:

- LangGraph state model
- router, chat, clarify, dispatch, and result nodes
- human-input pause/resume flow
- tool registry built from dependency injection

Exit criteria:

- one thread per `session_id`
- pending human-input requests resume correctly
- routing tests cover tool call, clarify, and chat branches
- no tool depends on module-level service globals

## Phase 4: Browser Runtime and Critical Tools

Goal: automate the real attendance flow end to end.

Scope:

- shared browser process and per-user contexts
- `login_to_dys`
- `join_teams_meeting`
- `take_screenshot`
- `leave_meeting`
- meeting state machine

Exit criteria:

- login and join work in mocked integration tests
- screenshots are captured from active sessions only
- 2FA and waiting-room flows degrade gracefully
- meeting state transitions are explicit and test-covered

## Phase 5: Scheduling, Queueing, and Recovery

Goal: move from request-response behavior to reliable automation.

Scope:

- APScheduler job creation from durable courses
- Celery task execution
- `T-3` and `T-1` notifications
- restart-time session recovery by fresh login
- deduplication and idempotency protections

Exit criteria:

- scheduled courses enqueue exactly one join flow
- restart recovery uses fresh browser contexts
- duplicate jobs do not launch duplicate meeting joins
- audit events reflect scheduling and recovery actions

## Phase 6: Production Hardening

Goal: make the system supportable under real multi-tenant usage.

Scope:

- rate limiting
- abuse controls
- metrics and dashboards
- task visibility and operational tooling
- Docker health checks and deploy polish
- backup and recovery procedures

Exit criteria:

- observability baseline is available without ad hoc debugging
- abuse controls block obvious misuse patterns
- service health is externally visible
- deployment checklist is documented and reproducible

## Phase 7: Expansion Features

Goal: add value without weakening the core system.

Scope:

- `read_teams_chat`
- schedule editing commands
- improved conflict resolution
- university-specific adapters
- richer admin and support tooling

Exit criteria:

- each new feature has tests, docs, and failure behavior
- experimental adapters are labeled clearly
- core attendance flow remains stable

## Definition of "Working System"

The system should only be described as working once Phases 1 through 5 are complete. Before that, it may contain useful vertical slices, but it is not yet an operational attendance agent.
