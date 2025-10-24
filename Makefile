.PHONY: build build-dev up down logs test debug clean help

# Variables
SERVICE_PROXY := lampa-proxy
SERVICE_TESTS := lampa-proxy-tests
SERVICE_DEBUG := lampa-proxy-debug

DOCKER_COMPOSE := docker-compose

# Default target
help:
	@echo "Available targets:"
	@echo "  build        - Build production image"
	@echo "  build-dev    - Build development image"
	@echo "  build-tests  - Build tests image"
	@echo "  up           - Start production service"
	@echo "  down         - Stop all services"
	@echo "  logs         - Show production service logs"
	@echo "  test         - Run tests"
	@echo "  debug        - Start debug service"
	@echo "  clean        - Remove all containers and images"

# Build targets
build:
	$(DOCKER_COMPOSE) build $(SERVICE_PROXY)

build-dev:
	$(DOCKER_COMPOSE) build $(SERVICE_DEBUG)

build-tests:
	$(DOCKER_COMPOSE) build $(SERVICE_TESTS)

# Service management
up: build
	$(DOCKER_COMPOSE) up -d $(SERVICE_PROXY)

down:
	$(DOCKER_COMPOSE) down

logs:
	$(DOCKER_COMPOSE) logs -f $(SERVICE_PROXY)

# Development
test: build-tests
	$(DOCKER_COMPOSE) run --rm $(SERVICE_TESTS)

debug: build-dev
	$(DOCKER_COMPOSE) up $(SERVICE_DEBUG) --build --force-recreate

# Cleanup
clean:
	$(DOCKER_COMPOSE) down -v --rmi all

# Utility targets
ps: build
	$(DOCKER_COMPOSE) ps

images:
	$(DOCKER_COMPOSE) images

# Shortcut aliases
dev: debug
tests: test
start: up
stop: down