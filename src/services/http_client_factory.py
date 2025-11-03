import logging
from typing import Dict, AsyncGenerator
from contextlib import asynccontextmanager
import httpx

from src.models.interfaces import IHttpClientFactory, IConfig, ITimeoutConfigurator


class HttpClientFactory(IHttpClientFactory):
    """Фабрика HTTP клиентов"""

    def __init__(self, config: IConfig, timeout_configurator: ITimeoutConfigurator):
        self.config = config
        self.timeout_configurator = timeout_configurator
        self.logger = logging.getLogger('lampa-proxy-http-factory')
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

    async def cleanup(self):
        for client_key, client in self._client_cache.items():
            try:
                await client.aclose()
                self.logger.debug(f"Closed cached client: {client_key}")
            except Exception as e:
                self.logger.warning(f"Error closing cached client {client_key}: {str(e)}")

        self._client_cache.clear()

