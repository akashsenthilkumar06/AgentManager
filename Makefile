.PHONY: install install-frontend dev dev-backend dev-frontend app test test-native check build-frontend

install:
	python3 -m pip install -e '.[dev]'
	cd frontend && npm install

install-frontend:
	cd frontend && npm install

dev:
	.venv/bin/python scripts/dev.py

dev-backend:
	uvicorn backend.app.main:app --reload

dev-frontend:
	cd frontend && npm run dev

app:
	./AgentManagerNative/agent-manager-native

test-native:
	swift test --package-path AgentManagerNative

build-frontend:
	cd frontend && npm run build

test:
	pytest

check:
	python3 -m compileall -q backend
	cd frontend && npm run check
	cd frontend && npm run build
	pytest
