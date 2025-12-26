.PHONY: help up down logs test clean

help:
	@echo "Available targets:"
	@echo "  make up       - Start Docker containers"
	@echo "  make down     - Stop Docker containers"
	@echo "  make logs     - View container logs"
	@echo "  make test     - Run test suite"
	@echo "  make clean    - Remove containers and volumes"

up:
	docker-compose up -d
	@echo "✓ Application started on http://localhost:8000"

down:
	docker-compose down
	@echo "✓ Application stopped"

logs:
	docker-compose logs -f webhook-api

test:
	docker-compose exec webhook-api pytest -v /app/tests/

clean:
	docker-compose down -v
	@echo "✓ Cleaned up containers and volumes"

.DEFAULT_GOAL := help
