.PHONY: up down logs test lint frontend clean

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f

test:
	cd services/auth && pip install -r requirements.txt --break-system-packages -q && pytest -q
	cd services/gateway && pip install -r requirements.txt --break-system-packages -q && pytest -q
	cd services/deployment && pip install -r requirements.txt --break-system-packages -q && pytest -q
	cd services/incident && pip install -r requirements.txt --break-system-packages -q && pytest -q
	cd services/alert && pip install -r requirements.txt --break-system-packages -q && pytest -q
	cd services/aiops && pip install -r requirements.txt --break-system-packages -q && pytest -q
	cd services/analytics && pip install -r requirements.txt --break-system-packages -q && pytest -q
	cd services/notification && pip install -r requirements.txt --break-system-packages -q && pytest -q
	cd services/audit && pip install -r requirements.txt --break-system-packages -q && pytest -q
	cd services/infrastructure && pip install -r requirements.txt --break-system-packages -q && pytest -q

lint:
	pip install ruff --break-system-packages -q
	ruff check services/

frontend:
	cd frontend && pnpm install --frozen-lockfile && pnpm run build

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
