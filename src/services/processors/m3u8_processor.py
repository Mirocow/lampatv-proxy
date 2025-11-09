import re
import urllib.parse
from typing import Dict, Any, AsyncGenerator

from src.utils.url_utils import encode_base64_url
from src.utils.logger import get_logger
from src.models.interfaces import IRequestProcessor, IConfig, IHttpClientFactory, IProxyGenerator, ITimeoutConfigurator
from src.models.responses import ProxyResponse


URL_PATTERN = re.compile(r'https?://[^\s"\',]+|/[^\s"\',]*', flags=re.IGNORECASE)


class M3U8Processor(IRequestProcessor):
    """Основной процессор контента"""

    def __init__(self,
                 config: IConfig,
                 http_factory: IHttpClientFactory,
                 proxy_generator: IProxyGenerator,
                 timeout_configurator: ITimeoutConfigurator,
                 request_processor: IRequestProcessor):
        self.config = config
        self.http_factory = http_factory
        self.proxy_generator = proxy_generator
        self.timeout_configurator = timeout_configurator
        self.request_processor = request_processor
        self.logger = get_logger('m3u8-processor', self.config.log_level)

    async def process_request(self,
                           target_url: str,
                           method: str = 'GET',
                           data: Any = None,
                           headers: Dict = None) -> AsyncGenerator[ProxyResponse, None]:
        """Обрабатывает m3u8 плейлист, подменяя домены на наш"""

        return await self._process_m3u8_playlist(target_url, headers)

    async def _process_m3u8_playlist(self, target_url: str, headers: Dict) -> ProxyResponse:
        """Обрабатывает m3u8 плейлист, подменяя домены на наш"""
        try:
            self.logger.info(f"Processing m3u8 playlist: {target_url}")

            request_headers = headers.copy()

            proxy = await self.proxy_generator.get_proxy() if self.proxy_generator.has_proxies() else None

            timeout_multiplier = 1
            if proxy:
                timeout_multiplier = 10

            # Создаем таймаут для запроса
            timeout = self.timeout_configurator.create_timeout_config(timeout_multiplier)

            # Получаем содержимое m3u8 плейлиста
            async with self.http_factory.create_client(
                headers=request_headers,
                is_video=False,
                follow_redirects=False,
                verify_ssl=False,
                proxy=proxy,
                timeout=timeout
            ) as client:

                response = await client.get(target_url)

                self.logger.info(f"Response status: {response.status_code}")

                if response.status_code == 200:

                    # Подменяем домены в плейлисте
                    modified_content = self._replace_domains_in_m3u8(response.text, target_url)

                    return ProxyResponse(
                        currentUrl=str(target_url),
                        cookie=[],
                        headers={
                            'Content-Type': 'application/vnd.apple.mpegurl',
                            'Cache-Control': 'no-cache'
                        },
                        status=response.status_code,
                        body=modified_content
                    )

        except Exception as e:
            self.logger.error(f"Error processing m3u8 playlist: {str(e)}")
            raise e

            # В случае ошибки возвращаем оригинальный контент
            # async for result in self.request_processor.process_request(target_url, method, data, headers):
            #     return result

    def _replace_domains_in_m3u8(self, content: str, base_url: str) -> str:
        """Упрощенная замена доменов в m3u8 плейлисте"""
        try:
            if not self.config.our_domain:
                return content

            # Простой поиск и замена всех URL в контенте
            def replace_url(match):
                url = match.group(0)
                if not url.startswith(('http://', 'https://')):
                    url = urllib.parse.urljoin(base_url, url)

                parsed = urllib.parse.urlparse(url)
                if parsed.netloc:  # Если есть домен - заменяем
                    return f"{self.config.our_scheme}://{self.config.our_domain}/enc2/{encode_base64_url(url)}"

                return url

            # Заменяем все URL в контенте
            return URL_PATTERN.sub(replace_url, content)

        except Exception as e:
            self.logger.error(f"Error replacing domains in m3u8: {str(e)}")
            return content
