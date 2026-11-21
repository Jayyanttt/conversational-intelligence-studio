.PHONY: up down restart logs reset
up:
	docker compose up --build
down:
	docker compose down
restart:
	docker compose restart
logs:
	docker compose logs -f
# Deletes the SQLite volume (all chat history).
reset:
	docker compose down -v
