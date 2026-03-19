# Contributing

## Development Philosophy

This project is intentionally being built in phases. Favor small, reversible changes that strengthen contracts before adding more surface area.

Before starting implementation work, check:

- [AGENTS.md](AGENTS.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)

If a change conflicts with those documents, align the documents first or update them in the same change.

## Workflow

1. Create a branch from the current mainline
2. Write or update tests first when touching behavior
3. Implement the change in the smallest meaningful slice
4. Run `ruff check .`, `mypy .`, and `pytest`
5. Update `CHANGELOG.md` under `[Unreleased]`
6. Update docs when architecture, behavior, or configuration changes
7. Open a PR with scope, risks, and validation notes

## Branch Naming

- `feat/` for new features
- `fix/` for bug fixes
- `chore/` for tooling, dependencies, or config
- `docs/` for documentation-only changes

## Commit Style

Use Conventional Commits.

```text
feat(agent): add human input resume flow
fix(schedule): normalize local times before UTC conversion
docs(architecture): define celery as the only queue runtime
```

## Code Standards

- Python 3.11+, fully async application code
- `ruff` for linting and formatting
- `mypy` strict mode
- Pydantic v2 for external schemas and config
- `structlog` for logging, no `print()`
- Every public function has type annotations
- No module-level mutable service singletons
- Browser-use for semantic navigation, Playwright for deterministic browser primitives

## Testing Expectations

- Unit tests in `tests/unit/` mock all external I/O
- Integration tests in `tests/integration/` use real graph wiring with mocked browser dependencies
- Migration changes must be reversible
- Security-sensitive behavior must include negative-path tests
- Coverage target remains at least 80%

## Documentation Expectations

Update docs whenever you change:

- queue/runtime behavior
- data ownership
- security posture
- onboarding flow
- schedule parsing or confirmation behavior
- operator workflows

README should stay concise and user-facing. `AGENTS.md` and `docs/ARCHITECTURE.md` should hold the deeper implementation contracts.

## No-Go Items

- No plaintext credentials in code, fixtures, logs, or screenshots
- No blocking I/O in async paths
- No hardcoded selectors as the main automation strategy
- No silent retries for auth failures
- No merge to `main` without green CI
