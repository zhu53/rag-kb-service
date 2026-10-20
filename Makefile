.PHONY: help install dev test cov lint fmt type check up down

help:
	@echo "install : uv sync --group dev"
	@echo "dev     : 启动开发服务器"
	@echo "test    : 运行测试"
	@echo "cov     : 测试 + 覆盖率报告"
	@echo "check   : lint + type 一起跑（提交前必跑）"
	@echo "up/down : 起停 postgres + redis"

install:
	uv sync --group dev

dev:
	uv run uvicorn kb_service.main:app --reload --port 8000

test:
	uv run pytest -q

cov:
	uv run pytest --cov=src/kb_service --cov-report=term-missing

lint:
	uv run ruff check . --fix
	uv run ruff format .

type:
	uv run mypy src

check: lint type test

up:
	docker compose up -d

down:
	docker compose down
