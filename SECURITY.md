# Security Policy

## Security Principles

- least persistence for sensitive browser state
- explicit ownership and auditability for user actions
- secure defaults before convenience
- clear recovery flows instead of hidden magic

## Sensitive Data Handling

- Student credentials are encrypted before storage with AES-256 using the application secret key
- Telegram chat IDs are treated as personal data and should not be emitted in plaintext logs in production
- Session cookies live only in memory inside the active browser context
- Session cookies are never written to disk, Redis, or PostgreSQL
- Screenshots must be treated as sensitive artifacts and stored for the shortest practical retention window
- `.env` must never be committed

## Session Recovery Model

After a process or container restart:

- browser contexts are gone
- cookies are gone
- active runtime state must be rebuilt from durable records
- recovery happens by creating a fresh browser context and re-running login if needed

This project does not persist browser sessions across restarts.

## Key Management Expectations

Current baseline:

- one application secret encrypts credentials at rest
- the key is read from `SECRET_KEY`

Forward-looking production expectation:

- secrets should come from a secret manager or deployment platform secret store, not from committed files
- key versioning and controlled credential re-encryption should be planned before general availability
- rotation procedures must include an audit trail and rollback path

## Audit and Observability

The system should produce immutable audit events for:

- onboarding completion
- credential updates
- login success and login failure
- human-input requests and resolutions
- meeting join and leave actions
- automatic recovery attempts

Audit data must not include decrypted credentials or raw secret values.

## Abuse and Safety Controls

Minimum required controls:

- per-user rate limiting on Telegram-triggered actions
- one active session per user
- cooldown after repeated failed login attempts
- deduplication of repeated join requests

## Reporting a Vulnerability

Do not open a public issue for a suspected security problem.

Contact: `security@YOUR_DOMAIN`

Include:

- affected component
- reproduction steps
- expected impact
- whether the issue exposes user data or cross-tenant isolation risk

You should receive an initial response within 72 hours.

## Scope

In scope:

- credential encryption
- session isolation
- tenant separation
- Telegram command handling
- browser automation boundaries
- Docker and deployment secrets handling

Out of scope:

- vulnerabilities that exist only in upstream dependencies and should be reported upstream first
