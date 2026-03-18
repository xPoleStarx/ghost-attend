.PHONY: dev test lint typecheck migrate setup logs shell test-e2e makemigration

dev:
	bash ./scripts/dev.sh up

rebuild:
	bash ./scripts/dev.sh rebuild

test:
	bash ./scripts/dev.sh test

test-e2e:
	docker compose -f docker-compose.test.yml up --abort-on-container-exit

lint:
	poetry run ruff check src/ tests/ --fix

typecheck:
	poetry run mypy src/

migrate:
	bash ./scripts/dev.sh migrate

makemigration:
	docker compose run --rm bot alembic revision --autogenerate -m "$(name)"

setup:
	./scripts/setup.sh

logs:
	bash ./scripts/dev.sh logs

shell:
	docker compose exec bot python
