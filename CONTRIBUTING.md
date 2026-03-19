# Contributing

Thanks. Small, focused changes are the easiest to merge.

**Maintainer:** Seyfullah Korkmaz — for project-related questions, contact [seyfullahkorkmaz115@gmail.com](mailto:seyfullahkorkmaz115@gmail.com).

## Development setup

1. Clone the repo and follow [README.md](README.md) (prefer `Run.ps1` / `Run.sh`).
2. Do **not** commit `.env`; use `.env.example` as a template.
3. Tests: from the project root, `python -m pytest` (or `make test`).

## Pull requests

- Prefer one topic per PR.
- Keep `pytest` green when possible.
- Do not add API keys, tokens, or personal data.

## Reporting issues

When reporting bugs, please include: OS, Python version, relevant `.env` keys **without values** (e.g. “Gemini 400”), and short steps to reproduce.
