.PHONY: up down test lint install

## Start the full platform stack (Redis + World Model)
up:
	docker compose up --build -d
	@echo "World Model → http://localhost:8010"
	@echo "World Model docs → http://localhost:8010/docs"

## Tear down all services
down:
	docker compose down -v

## Run World Model tests (requires: pip install -e .[dev] in sentinel_sdk)
test:
	cd world_model && \
	  PYTHONPATH=src:../../ pytest tests/ -v

## Install the sentinel_sdk package in editable mode
install:
	pip install -e ".[dev]"

## Lint with ruff (optional)
lint:
	ruff check . --select E,F,W --ignore E501
