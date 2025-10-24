# JsonP Proxy Server

* lampa-proxy - основной сервер

## Сборка и запуск 

### Сборка и запуск
make build      # Сборка production-образа
make up         # Запуск сервиса в фоне
make logs       # Просмотр логов

### Разработка
make build-dev  # Сборка development-образа
make test       # Запуск тестов
make debug      # Запуск в режиме отладки

### Управление
make down       # Остановка сервисов
make ps         # Просмотр статуса контейнеров
make clean      # Полная очистка (контейнеры и образы)

### Псевдонимы
make dev        # Аналогично debug
make tests      # Аналогично test
make stop       # Аналогично down
