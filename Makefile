.PHONY: dev test lint typecheck migrate setup logs shell test-e2e makemigration

dev:
	docker compose -f docker-compose.dev.yml up

test:
	poetry run pytest tests/unit tests/integration -v --cov=src

test-e2e:
	docker compose -f docker-compose.test.yml up --abort-on-container-exit

lint:
	poetry run ruff check src/ tests/ --fix

typecheck:
	poetry run mypy src/

migrate:
	docker compose run --rm bot alembic upgrade head

makemigration:
	docker compose run --rm bot alembic revision --autogenerate -m "$(name)"

setup:
	./scripts/setup.sh

logs:
	docker compose logs -f bot worker

shell:
	docker compose exec bot python
