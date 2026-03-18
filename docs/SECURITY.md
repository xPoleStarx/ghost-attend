# Security Policy

GhostAttend handles automation credentials, session state, and browser activity. As a result, security expectations for this repository are higher than for a typical demo project.

This document describes the current security posture, the main trust boundaries, and the expected disclosure process for vulnerabilities.

## Security Model

GhostAttend is designed as a self-hosted system:

- the deployer controls the infrastructure
- credentials remain within the deployer's environment
- no central hosted credential service is part of the architecture
- browser automation runs inside containers controlled by the deployer

This reduces third-party exposure, but it also means the operator is responsible for securing the host, Docker runtime, environment files, and bot token.

## Sensitive Assets

The most sensitive assets in this project are:

- Telegram bot token
- DYS / university portal credentials
- session cookies
- MFA codes
- `MASTER_ENCRYPTION_KEY`
- database and Redis connection credentials

## Current Protections

### Credentials and encryption

- credentials are encrypted before persistence
- `MASTER_ENCRYPTION_KEY` is loaded from environment and not stored in the database
- plaintext credentials should never be logged
- cookies are treated as sensitive credential-equivalent material

### Telegram interaction safety

- password and MFA flows are designed to minimize exposure in chat history
- secret-bearing messages should be deleted as early as possible in the conversation flow
- user-facing prompts should avoid echoing sensitive values back into the chat

### Container runtime

- containers run as non-root where configured
- worker and scheduler browser execution is forced into headless mode in containers
- environment files are expected to remain local and out of version control

### Operational visibility

- logs should make failures diagnosable without exposing secrets
- runtime should distinguish real task success from business-failure states
- screenshots and notifications should be reviewed as potentially sensitive operational artifacts

## Operator Responsibilities

If you deploy GhostAttend, you are responsible for:

- securing the host machine or VPS
- restricting access to `.env`
- protecting Docker daemon access
- rotating secrets when compromise is suspected
- reviewing whether your institution or platform rules allow the intended usage

## Supported Reporting Process

If you discover a security issue, please do not open a public GitHub issue.

Instead:

1. prepare a short description of the issue
2. include impact, affected components, and reproduction notes if possible
3. share it privately with the maintainer or repository owner through a non-public channel

If a private reporting contact is added later, this document should be updated accordingly.

## What to Include in a Security Report

A useful report should include:

- affected component or file
- impact assessment
- realistic attack path
- whether credentials, tokens, or cookies can be exposed
- whether the issue requires local access, chat access, or infrastructure access
- suggested mitigation if available

## Rotation Guidance

Rotate secrets immediately if compromise is suspected.

Typical rotation targets:

- Telegram bot token
- `MASTER_ENCRYPTION_KEY`
- PostgreSQL password
- Redis password
- stored DYS credentials
- stored session cookies

After rotating secrets, rebuild or restart affected services so they re-read runtime configuration.

## Secure Development Guidance

When contributing to this repository:

- never commit `.env`
- never commit real credentials or cookies
- avoid pasting production secrets into issues, PRs, or screenshots
- treat logs as potentially sensitive artifacts
- prefer safe-by-default Docker and runtime behavior
- document any security tradeoff introduced by a change

Changes affecting the following areas should be reviewed with extra care:

- `src/security/`
- `src/bot/handlers/credentials.py`
- `src/bot/handlers/mfa.py`
- `src/agent/runner.py`
- `scripts/setup.*`
- `docker-compose*.yml`

## Out of Scope

This repository cannot guarantee compliance with:

- university policies
- conferencing platform terms of service
- institution-specific automation restrictions

Those remain the responsibility of the deployer.

## License and Warranty Context

GhostAttend is distributed under the MIT License. As with the license itself, the software is provided without warranty. That does not reduce the expectation that known vulnerabilities be handled responsibly, but it does mean deployers must evaluate fitness and risk for their own environment.
