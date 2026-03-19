# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Added [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) to define the authoritative runtime contracts
- Added [docs/ROADMAP.md](docs/ROADMAP.md) with phased delivery milestones and exit criteria
- Added the initial application scaffold with config, DI container, DB models, Alembic setup, browser interfaces, tool contracts, scheduler and worker skeletons
- Added the first security and domain services, including credential encryption, schedule parsing, idempotency helpers, and initial tests
- Added Phase 2 onboarding services for step-based Telegram onboarding, schedule ingestion, confirmation flow, and schedule activation persistence
- Added Phase 3 agent runtime components for intent classification, dependency-aware tool dispatch, human-input resume flow, and agent runtime tests
- Added Phase 4 browser runtime behavior for login, join, waiting room, screenshots, leave flow, and mocked browser tool integration tests
- Added Phase 5 scheduling and recovery foundations for job planning, task queue dispatch, duplicate-safe scheduler records, and active-session recovery coordination
- Added Phase 6 hardening foundations for rate limiting, duplicate-command protection, conflict detection, observability metrics, and operator runtime snapshots
- Added application integration wiring for runtime bootstrap, request-scoped containers, Telegram command handling, bot service orchestration, and startup scheduler/recovery initialization
- Added live-oriented scheduler loop and Playwright-capable browser runtime wiring, moving browser automation and recurring scheduling closer to production behavior
- Simplified clone-and-boot experience with automatic DB wait/migrations, standby mode without Telegram token, and setup scripts for creating `.env`

### Changed

- Standardized the queue architecture on Redis + Celery
- Clarified the Browser-use versus Playwright responsibility boundary
- Reframed restart handling as session recovery via fresh login, not browser-context restore
- Moved durable course ownership to the user model instead of the session model
- Defined a concrete human-input workflow contract and explicit meeting runtime states
- Narrowed university support claims to validated or experimental compatibility levels
- Expanded documentation around observability, abuse controls, and forward-looking secrets management

---

<!-- Example entries for future use:

## [0.2.0] - 2026-MM-DD
### Added
- `read_teams_chat` tool
### Fixed
- UTC offset bug in APScheduler for DST transitions
### Changed
- `take_screenshot` now waits for `networkidle` before capture

## [0.1.0] - 2026-MM-DD
### Added
- Initial working bot: onboarding, session lifecycle, join/leave tools
-->
