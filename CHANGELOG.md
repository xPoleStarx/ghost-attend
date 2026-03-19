# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Added [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) to define the authoritative runtime contracts
- Added [docs/ROADMAP.md](docs/ROADMAP.md) with phased delivery milestones and exit criteria

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
