.PHONY: up down restart logs build clean

up:
	docker compose up -d --build
	@echo ""
	@echo "Server is running at http://localhost:8000"
	@echo "Check health: curl http://localhost:8000/health"

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

build-extension:
	cd extension && npm install && npm run build
	@echo ""
	@echo "Extension built. Load extension/dist in Chrome (see README)."

clean:
	docker compose down -v
	@echo "Stopped containers and removed data volume."
