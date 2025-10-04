.PHONY: build run stop clean test

# Основные команды
build:
	docker-compose build

lock:
	docker run --rm -v "$(PWD):/app" python:3.13-slim \
		sh -c "pip install poetry==1.8.2 && cd /app && poetry lock --no-update"

check-lock:
	poetry lock --check

recreate:
	docker-compose up -d --build --force-recreate

run:
	docker-compose up -d

stop:
	docker-compose down

clean:
	docker-compose down -v --rmi all

logs:
	docker-compose logs -f

# Для разработки
dev:
	docker-compose up

# Тестирование
test:
	docker-compose run --rm dns-http-server python -c "import dnslib; print('DNSLib version:', dnslib.__version__)"

# Управление зависимостями
update-deps:
	docker-compose run --rm dns-http-server poetry update
	# ИЛИ для requirements.txt:
	# docker-compose run --rm dns-http-server pip freeze > requirements.txt

# Сборка для продакшена
prod-build:
	docker build --no-cache -t dns-http-server:prod .

prod-run:
	docker run -d \
		-p 80:80 \
		-p 443:443 \
		-p 53:53/udp \
		--name dns-http-server \
		dns-http-server:prod