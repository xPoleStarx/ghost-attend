# Contributing

Thank you for considering a contribution to GhostAttend.

This repository combines Telegram automation, browser orchestration, scheduling, and credential handling. Changes should therefore optimize for reliability, observability, and operational safety rather than only local correctness.

## Before You Start

Please read these documents first:

- [README.md](../README.md)
- [docs/SETUP.md](./SETUP.md)
- [docs/SECURITY.md](./SECURITY.md)
- [architecture.md](../architecture.md)

## Development Setup

The recommended development flow is to use the project helper scripts instead of hand-writing long Docker commands.

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 up
```

### Linux / macOS

```bash
bash scripts/setup.sh
./scripts/dev.sh up
```

Common operations:

- start services: `dev up`
- rebuild services: `dev rebuild`
- stream logs: `dev logs`
- run migrations: `dev migrate`
- run tests: `dev test`

## Contribution Principles

We prioritize:

- correctness over cleverness
- explicit behavior over hidden magic
- safe defaults in Docker and production-like environments
- logs and failure visibility for operator-facing flows
- tests for behavior that can regress in distributed runtime paths

## Pull Request Expectations

A good pull request should:

- solve one coherent problem
- include tests when behavior changes
- preserve or improve operator visibility
- avoid unrelated formatting churn
- document any operational impact

## Coding Guidelines

### General

- Use Python 3.11 compatible code.
- Prefer clear, deterministic behavior over speculative heuristics.
- Keep functions small when possible, but favor readability over artificial fragmentation.
- Add comments only where the code would otherwise be hard to follow.

### Bot and workflow changes

If you modify Telegram flows, consider:

- first-time user clarity
- what happens when the user sends vague or partial input
- whether state is recoverable after restart
- whether the message shown to the user matches the actual runtime outcome

### Worker and scheduler changes

If you modify worker or scheduler behavior, consider:

- container runtime constraints
- headless browser requirements
- retry semantics
- whether task success and failure are reported consistently
- whether Docker rebuild is required after your change

## Testing Expectations

At minimum, run the tests relevant to your change.

Recommended checks:

- unit and integration tests for behavior changes
- compile/syntax checks if the local environment lacks pytest
- manual smoke verification for Docker, scheduling, or Playwright changes

Examples:

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 test
```

### Linux / macOS

```bash
./scripts/dev.sh test
```

If your environment does not have `pytest` available locally, mention that clearly in the PR or change summary.

## Branch and Commit Guidance

There is no strict naming rule enforced by the repository, but the following conventions are recommended:

- `feature/<short-name>`
- `fix/<short-name>`
- `docs/<short-name>`
- `chore/<short-name>`

Recommended commit style:

- `feat: add deterministic manual join matching`
- `fix: force headless browser mode in worker containers`
- `docs: improve setup and developer workflow documentation`

## Security-Sensitive Areas

Changes in the following areas require extra care:

- credential storage and encryption
- `.env` generation or parsing
- session cookies
- Docker permissions and network exposure
- Telegram message deletion for secrets and MFA codes

If you touch these areas, please explain the reasoning and testing approach in the PR description.

## Reporting Issues

Use GitHub Issues for:

- bugs
- feature requests
- documentation gaps
- onboarding friction

Do not open a public issue for a security vulnerability. Follow [docs/SECURITY.md](./SECURITY.md) instead.

## Documentation Contributions

Documentation changes are welcome and valuable.

If you change operational behavior, update the relevant documents in the same PR:

- `README.md` for user-facing quick start and operations
- `docs/SETUP.md` for installation and troubleshooting
- `architecture.md` for important architectural or workflow decisions
- `docs/SECURITY.md` when behavior affects credential, runtime, or reporting safety
