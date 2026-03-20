# Contributing to GhostMyShit

Thanks for helping improve the project. We optimize for **small, reviewable changes**, clear communication, and **no secrets in the repo**.

**Maintainer:** Seyfullah Korkmaz — [seyfullahkorkmaz115@gmail.com](mailto:seyfullahkorkmaz115@gmail.com)

## Community standards

Be direct, be kind, and assume good intent. Disagreement is fine; harassment is not. Keep discussion focused on the code and the user impact.

## Before you start

- Read [README.md](README.md) for architecture and [QUICKSTART.md](QUICKSTART.md) for setup.
- Never commit `.env` or real tokens. Use [`.env.example`](.env.example) as the template only.
- **Dependency source of truth:** [`pyproject.toml`](pyproject.toml). Do not “fix” installs by pinning random versions in [`requirements.txt`](requirements.txt) unless the maintainer explicitly agrees—editable installs use the package metadata.

## Development setup

1. Clone: `git clone https://github.com/xPoleStarx/GhostMyShit.git`
2. Create `.env` from `.env.example` (local only).
3. Prefer **`Run.ps1`** (Windows) or **`Run.sh`** (Linux/macOS), or follow the manual path in [QUICKSTART.md](QUICKSTART.md).
4. Install dev extras and run tests:

   ```bash
   python -m pip install -e ".[dev]"
   python -m pytest
   ```

## Branching

- **`main`** is the integration branch; keep it releasable.
- Use short-lived topic branches, for example:
  - `feat/short-description`
  - `fix/issue-short-description`
  - `docs/what-changed`

## Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/) (summary line + optional body):

| Prefix | Use when |
|--------|-----------|
| `feat:` | New user-visible behavior |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `test:` | Tests only |
| `chore:` | Tooling, CI, formatting that is not a feature/fix |
| `refactor:` | Internal change, same behavior |

Examples:

- `feat: add timeout hint when browser step stalls`
- `fix: handle empty HITL reply without crashing`
- `docs: clarify Docker volume for checkpoints`

**Breaking changes:** add `!` after the type (e.g. `feat!: remove legacy env var`) **or** a footer `BREAKING CHANGE: ...` with migration notes.

## Pull requests

1. Open a PR against **`main`**.
2. Fill in **[`.github/pull_request_template.md`](.github/pull_request_template.md)** completely (summary, type, testing, checklist).
3. **One topic per PR** — large mixed refactors are hard to review and risky to bisect.
4. Keep diffs focused; avoid drive-by renames or unrelated formatting.
5. Ensure **`python -m pytest`** passes, or explain clearly why not (e.g. docs-only with no test impact).
6. Do not paste API keys, Telegram tokens, personal data, or full `.env` contents in issues or PRs.

## Code guidelines

- Match existing module layout under `app/` and naming style.
- Prefer **async-safe** patterns where the codebase is already async (Telegram handlers, graph, browser runner).
- New behavior that can be unit-tested should include tests; if not practical, state why in the PR.

## Reporting issues

Include:

- OS and version  
- Python version (`python --version`)  
- How you run the bot (script, manual venv, Docker)  
- Steps to reproduce  
- Relevant log excerpts (redact secrets)  
- Names of `.env` keys involved **without values** (e.g. `GEMINI_MODEL`, `PLAYWRIGHT_HEADLESS`)

## Security

If you believe you found a **security vulnerability**, email **Seyfullah Korkmaz** at [seyfullahkorkmaz115@gmail.com](mailto:seyfullahkorkmaz115@gmail.com) **before** opening a public issue, so we can coordinate a fix and disclosure.

---

**Repository:** [github.com/xPoleStarx/GhostMyShit](https://github.com/xPoleStarx/GhostMyShit)
