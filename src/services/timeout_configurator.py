import httpx

from src.models.interfaces import ITimeoutConfigurator, IConfig


class TimeoutConfigurator(ITimeoutConfigurator):
    """Класс для конфигурации таймаутов HTTP клиентов"""

    def __init__(self, config: IConfig):
        self.config = config

    def create_timeout_config(self, timeout_multiplier: int = 1) -> httpx.Timeout:
        """Создание таймаута для клиента"""

        return httpx.Timeout(
            connect=self.config.timeout_connect * timeout_multiplier,
            read=self.config.timeout_read * timeout_multiplier,
            write=self.config.timeout_write * timeout_multiplier,
            pool=self.config.timeout_pool * timeout_multiplier
        )
