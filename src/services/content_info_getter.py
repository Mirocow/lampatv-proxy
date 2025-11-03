import logging
import re
from typing import Dict
import httpx

from src.models.interfaces import IContentInfoGetter, IConfig, IHttpClientFactory, IProxyGenerator, ITimeoutConfigurator
from src.models.responses import ContentInfoResponse


class ContentInfoGetter(IContentInfoGetter):
    """Получение информации о контенте"""

    def __init__(self, config: IConfig, http_factory: IHttpClientFactory,
                 proxy_generator: IProxyGenerator, timeout_configurator: ITimeoutConfigurator):
        self.config = config
        self.http_factory = http_factory
        self.proxy_generator = proxy_generator
        self.timeout_configurator = timeout_configurator
        self.logger = logging.getLogger('lampa-proxy-content-getter')

    async def get_content_info(self, url: str, headers: Dict = None, use_head: bool = True) -> ContentInfoResponse:
        if headers is None:
            headers = {}

        try:
            if use_head:
                head_info = await self._try_head_request(url, headers)
                if head_info.content_length > 0:
                    return head_info

            get_info = await self._try_get_requests(url, headers)
            return get_info

        except Exception as e:
            self.logger.error(f"Failed to get content info for {url}: {str(e)}")
            return ContentInfoResponse(
                status_code=0,
                content_type='application/octet-stream',
                content_length=0,
                accept_ranges='bytes',
                headers={},
                method_used='ERROR',
                error=str(e)
            )

    async def _try_head_request(self, url: str, headers: Dict) -> ContentInfoResponse:
        try:
            self.logger.debug(f"Trying HEAD request for: {url}")
            proxy = await self.proxy_generator.get_proxy() if self.proxy_generator.has_proxies() else None

            timeout_multiplier = 10.0
            if proxy:
                timeout_multiplier = 30.0

            # Создаем таймаут для HEAD запроса
            timeout = self.timeout_configurator.create_timeout_config(timeout_multiplier)

            # Создаем запрос с учетом параметров
            async with self.http_factory.create_client(
                headers=headers,
                is_video=False,
                follow_redirects=True,
                verify_ssl=True,
                proxy=proxy,
                timeout=timeout
            ) as client:

                response = await client.head(url)

                content_length = 0
                if response.headers.get('content-length'):
                    try:
                        content_length = int(response.headers.get('content-length'))
                    except (ValueError, TypeError):
                        pass

                content_info = ContentInfoResponse(
                    status_code=response.status_code,
                    content_type=response.headers.get('content-type', ''),
                    content_length=content_length,
                    accept_ranges=response.headers.get('accept-ranges', 'bytes'),
                    headers=dict(response.headers),
                    method_used='HEAD'
                )

                if proxy:
                    await self.proxy_generator.mark_success(proxy)

                return content_info

        except Exception as e:
            self.logger.warning(f"HEAD request failed: {str(e)}")
            return ContentInfoResponse(
                status_code=0,
                content_type='',
                content_length=0,
                accept_ranges='bytes',
                headers={},
                method_used='HEAD',
                error=str(e)
            )

    async def _try_get_requests(self, url: str, headers: Dict) -> ContentInfoResponse:
        strategies = [
            {'Range': 'bytes=0-0', 'description': 'Range 0-0'},
            {'Range': 'bytes=0-999', 'description': 'Range 0-999'},
            {},
        ]

        for strategy in strategies:
            proxy = None
            try:
                strategy_headers = headers.copy()
                strategy_headers.update(strategy)

                self.logger.debug("Trying GET with strategy: %s", strategy.get('description', 'Simple GET'))
                proxy = await self.proxy_generator.get_proxy() if self.proxy_generator.has_proxies() else None

                timeout_multiplier = 10.0
                if proxy:
                    timeout_multiplier = 30.0

                # Создаем таймаут для GET запроса
                timeout = self.timeout_configurator.create_timeout_config(timeout_multiplier)

                # Создаем запрос с учетом параметров
                async with self.http_factory.create_client(
                    headers=strategy_headers,
                    is_video=False,
                    follow_redirects=True,
                    verify_ssl=True,
                    proxy=proxy,
                    timeout=timeout
                ) as client:

                    async with client.stream('GET', url) as response:
                        content_length = 0

                        # Парсим Content-Range для определения полного размера
                        if response.status_code == 206 and 'content-range' in response.headers:
                            content_range = response.headers['content-range']
                            match = re.match(r'bytes\s+\*?/?(\d+)-?(\d+)?/(\d+)', content_range)
                            if match:
                                content_length = int(match.group(3))

                        # Используем Content-Length если доступен
                        elif response.status_code == 200 and response.headers.get('content-length'):
                            try:
                                content_length = int(response.headers.get('content-length'))
                            except (ValueError, TypeError):
                                pass

                        content_info = ContentInfoResponse(
                            status_code=response.status_code,
                            content_type=response.headers.get('content-type', ''),
                            content_length=content_length,
                            accept_ranges=response.headers.get('accept-ranges', 'bytes'),
                            headers=dict(response.headers),
                            method_used=f"GET_{strategy.get('description', 'SIMPLE')}"
                        )

                        if proxy:
                            await self.proxy_generator.mark_success(proxy)

                        return content_info

            except Exception as e:
                self.logger.warning(f"GET strategy failed: {str(e)}")
                if proxy:
                    await self.proxy_generator.mark_failure(proxy)
                continue

        self.logger.warning(f"Could not determine content length for: {url}")
        return ContentInfoResponse(
            status_code=0,
            content_type='',
            content_length=0,
            accept_ranges='bytes',
            headers={},
            method_used='GET_ALL_FAILED',
            error="All GET strategies failed"
        )
