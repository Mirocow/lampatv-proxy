import re
import urllib.parse
from typing import Dict, Any, AsyncGenerator
import httpx

from src.utils.logger import get_logger
from src.models.interfaces import IRequestProcessor, IConfig, IHttpClientFactory, IProxyGenerator, ITimeoutConfigurator
from src.models.responses import ProxyResponse


URL_PATTERN = re.compile(r'(https?:/)([^/])', flags=re.IGNORECASE)


class RequestProcessor(IRequestProcessor):
    """Обработчик запросов"""

    def __init__(self,
                 config: IConfig,
                 http_factory: IHttpClientFactory,
                 proxy_generator: IProxyGenerator,
                 timeout_configurator: ITimeoutConfigurator):
        self.config = config
        self.http_factory = http_factory
        self.proxy_generator = proxy_generator
        self.timeout_configurator = timeout_configurator
        self.logger = get_logger('request-processor', self.config.log_level)

    async def process_request(self,
                           target_url: str,
                           method: str = 'GET',
                           data: Any = None,
                           headers: Dict = None) -> AsyncGenerator[ProxyResponse, None]:
        if headers is None:
            headers = {}

        self.logger.info(f"Processing {method} request to: {target_url}")
        target_url = self._normalize_url(target_url)

        proxy = None
        try:
            parsed = urllib.parse.urlparse(target_url)
            if not parsed.hostname:
                raise ValueError(f"Invalid hostname: {target_url}")

            request_headers = {
                'User-Agent': self.config.user_agent,
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,ru;q=0.7',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            }

            if headers:
                request_headers.update(headers)

            request_params = {}
            if method.upper() in ['POST', 'PUT', 'DELETE'] and data:
                if isinstance(data, dict):
                    request_params['data'] = data
                else:
                    request_params['content'] = data

            proxy = await self.proxy_generator.get_proxy() if self.proxy_generator.has_proxies() else None

            timeout_multiplier = 1
            if proxy:
                timeout_multiplier = 10

            # Создаем таймаут для запроса
            timeout = self.timeout_configurator.create_timeout_config(timeout_multiplier)

            # Создаем запрос с учетом параметров
            async with self.http_factory.create_client(
                headers=request_headers,
                is_video=False,
                follow_redirects=False,
                verify_ssl=False,
                proxy=proxy,
                timeout=timeout
            ) as client:

                response = await client.request(method, target_url, **request_params)

                self.logger.info(f"Response status: {response.status_code}")

                # Обрабатываем редиректы
                if response.status_code in [301, 302, 303, 307, 308]:
                    async for redirect_result in self._handle_redirect(response, request_headers, method, data):
                        yield redirect_result
                    return

                if proxy:
                    await self.proxy_generator.mark_success(proxy)

                # Собираем cookies
                cookies = []
                resp_headers = {}
                for name, value in response.headers.multi_items():
                    name_lower = name.lower()
                    if name_lower == 'set-cookie':
                        cookies.append(value)
                    resp_headers[name_lower] = value
                resp_headers['set-cookie'] = cookies

                yield ProxyResponse(
                    currentUrl=str(response.url),
                    cookie=cookies,
                    headers=resp_headers,
                    status=response.status_code,
                    body=response.text
                )

        except httpx.TimeoutException:
            self.logger.error(f"✕ Request timeout: {target_url}")
            yield ProxyResponse(
                currentUrl=target_url,
                cookie=[],
                headers={},
                status=408,
                body='',
                error='Request timeout'
            )

        except httpx.RequestError as e:
            self.logger.error(f"✕ Request failed: {target_url} - {str(e)}")
            if proxy:
                await self.proxy_generator.mark_failure(proxy)
            yield ProxyResponse(
                currentUrl=target_url,
                cookie=[],
                headers={},
                status=500,
                body='',
                error=f'Request failed: {str(e)}'
            )

        except Exception as e:
            self.logger.error(f"✕ Unexpected error: {target_url} - {str(e)}")
            if proxy:
                await self.proxy_generator.mark_failure(proxy)
            yield ProxyResponse(
                currentUrl=target_url,
                cookie=[],
                headers={},
                status=500,
                body='',
                error=f'Unexpected error: {str(e)}'
            )

    async def _handle_redirect(self, response, original_headers, method, data, redirect_count=0):
        if redirect_count >= self.config.max_redirects:
            raise ValueError(f"Too many redirects (max: {self.config.max_redirects})")

        if 'location' not in response.headers:
            raise ValueError("Redirect response without Location header")

        redirect_url = response.headers['location']
        self.logger.info(f"Following redirect {redirect_count + 1} to: {redirect_url}")

        if not redirect_url.startswith(('http://', 'https://')):
            parsed_original = urllib.parse.urlparse(str(response.url))
            base_url = f"{parsed_original.scheme}://{parsed_original.netloc}"
            redirect_url = urllib.parse.urljoin(base_url, redirect_url)

        async for result in self.process_request(redirect_url, method, data, original_headers):
            yield result

    def _normalize_url(self, url: str) -> str:
        if not url:
            raise ValueError("Empty URL")

        self.logger.debug(f"Original URL for normalization: {url}")

        protocols = ['https://', 'http://']
        for proto1 in protocols:
            for proto2 in protocols:
                duplicate = proto1 + proto2
                if url.startswith(duplicate):
                    url = url[len(proto1):]
                    self.logger.debug(f"Removed duplicate protocol: {url}")
                    break

        if url.startswith('//'):
            url = 'https:' + url
            self.logger.debug(f"Fixed protocol-relative URL: {url}")

        url = URL_PATTERN.sub(r'\1/\2', url)

        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        self.logger.debug(f"Normalized URL: {url}")
        return url
