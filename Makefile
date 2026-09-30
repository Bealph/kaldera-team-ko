.PHONY: up down test fmt lint typecheck install install-webapp webapp

install:
	uv sync

install-webapp:
	uv sync --extra webapp

webapp: install-webapp
	uv run python -m kaldera.webapp.app

up:
	docker compose up -d

down:
	docker compose down

test:
	uv run pytest -v

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

typecheck:
	uv run mypy src
