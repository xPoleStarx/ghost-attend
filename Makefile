# POSIX (Linux, macOS, Git Bash). Windows icin: Run.ps1 veya run.bat

.PHONY: install install-dev run test clean

install:
	python3 -m venv .venv
	./.venv/bin/python -m pip install --upgrade pip setuptools wheel
	./.venv/bin/python -m pip install -e .
	./.venv/bin/python -m playwright install chromium
	@test -f .env || (cp .env.example .env && echo "Olusturuldu: .env — token ve anahtari doldurun")

install-dev: install
	./.venv/bin/python -m pip install -e ".[dev]"

run:
	@test -f .venv/bin/python || (echo "Once: make install" && exit 1)
	PLAYWRIGHT_HEADLESS=false ./.venv/bin/python -m app.main

test:
	./.venv/bin/python -m pytest tests/ -v

clean:
	rm -rf .venv data/*.db 2>/dev/null || true
