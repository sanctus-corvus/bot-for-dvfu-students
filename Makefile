default: help

start:
	@echo "Запуск бота в Docker Compose..."
	docker compose up -d --build

stop:
	@echo "Остановка бота..."
	docker compose down

restart:
	@echo "Перезапуск бота..."
	docker compose restart

logs:
	@echo "Просмотр логов бота (нажмите Ctrl+C для выхода)..."
	docker compose logs -f

help:
	@echo "Доступные команды:"
	@echo "  make start        - Собрать образ (если нужно) и запустить бота в фоновом режиме"
	@echo "  make stop         - Остановить и удалить контейнер(ы) бота"
	@echo "  make restart      - Перезапустить контейнер(ы) бота"
	@echo "  make logs         - Показать логи бота в реальном времени"
	@echo "  make build        - Принудительно пересобрать образ без запуска"
	@echo "  make pull         - Скачать последнюю версию базового образа Python (если нужно)"
	@echo "  make clean        - Остановить контейнеры и удалить том с данными (ОСТОРОЖНО!)"

build:
	@echo "Принудительная пересборка образа..."
	docker compose build --no-cache

pull:
	@echo "Скачивание базового образа..."
	docker compose pull

clean: stop
	@echo "Удаление тома с данными (botdata)... ОСТОРОЖНО!"
	-docker volume rm $$(docker volume ls -q -f name=botdata) 2>/dev/null || true

.PHONY: default start stop restart logs help build pull clean