from typing import Dict, AsyncGenerator
from contextlib import asynccontextmanager
import httpx

from src.utils.logger import get_logger
from src.models.interfaces import IHttpClientFactory, IConfig, ITimeoutConfigurator


class HttpClientFactory(IHttpClientFactory):
    """Фабрика HTTP клиентов"""

    def __init__(self,
                 config: IConfig,
                 timeout_configurator: ITimeoutConfigurator):
        self.config = config
        self.timeout_configurator = timeout_configurator
        self.logger = get_logger('http-factory', self.config.log_level)
        self._client_cache = {}

    @asynccontextmanager
    async def create_client(self,
                          headers: Dict = None,
                          is_video: bool = False,
                          follow_redirects: bool = True,
                          verify_ssl: bool = False,
                          proxy: str = None,
                          timeout: httpx.Timeout = None) -> AsyncGenerator[httpx.AsyncClient, None]:

        if headers is None:
            headers = {}

        # Если timeout не передан, создаем его по умолчанию
        if timeout is None:
            timeout = self.timeout_configurator.create_timeout_config()

        client_params = {
            'headers': headers.copy(),
            'timeout': timeout,
            'follow_redirects': follow_redirects,
            'verify': verify_ssl
        }

        if proxy:
            client_params['proxy'] = proxy
            self.logger.info(f"Using specified proxy: {proxy}")

        client = httpx.AsyncClient(**client_params)
        try:
            yield client
        finally:
            await client.aclose()

    def get_client_cache_info(self) -> Dict:
        """Получение информации о кэше клиентов"""
        return {
            'cached_clients': len(self._client_cache),
            'config': {
                'timeout_connect': self.config.timeout_connect,
                'timeout_read': self.config.timeout_read,
                'timeout_write': self.config.timeout_write,
                'timeout_pool': self.config.timeout_pool,
            }
        }

    async def cleanup(self):
        for client_key, client in self._client_cache.items():
            try:
                await client.aclose()
                self.logger.debug(f"Closed cached client: {client_key}")
            except Exception as e:
                self.logger.warning(f"Error closing cached client {client_key}: {str(e)}")

        self._client_cache.clear()

