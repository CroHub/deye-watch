# Обгортки над docker compose. Якщо make на сервері немає — ті самі команди працюють напряму (див. README).
.DEFAULT_GOAL := help
.PHONY: help run build test lint logs ps restart stop info live dump tg

DC := docker compose
CLI := @mkdir -p data && $(DC) run --rm cli

help: ## список команд
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-8s %s\n", $$1, $$2}'

# --- бот ---

run: build test lint ## зібрати, прогнати тести й лінтер, (пере)запустити бот
	@mkdir -p data
	$(DC) up -d watch
	@sleep 3
	$(DC) logs --tail 20 watch

logs: ## логи бота (наживо)
	$(DC) logs -f --tail 100 watch

ps: ## стан контейнерів
	$(DC) ps

restart: ## перезапустити бот без перезбирання
	$(DC) restart watch

stop: ## зупинити бот
	$(DC) down

# --- інвертор (разово, з поточним кодом) ---

info: ## поточний стан інвертора
	$(CLI) info

live: ## живий дашборд, оновлення кожні SEC с (типово 5): make live SEC=2
	$(CLI) live $(SEC)

dump: ## сирі регістри: make dump FROM=150 TO=194
	$(CLI) dump $(or $(FROM),0) $(or $(TO),200)

tg: ## перевірити Telegram: користувачі + тестове повідомлення власнику
	$(CLI) tg

# --- розробка ---

build: ## зібрати образи deye (prod) і deye-dev (тести, лінтер)
	$(DC) --profile tools build watch test

test: ## тести (без інвертора й Telegram)
	$(DC) run --rm test

lint: ## ruff + mypy strict
	$(DC) run --rm lint
