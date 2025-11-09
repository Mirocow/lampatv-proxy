import httpx
from abc import ABC, abstractmethod
from typing import Dict, Optional, List, Any, AsyncGenerator
from fastapi.responses import StreamingResponse

from src.models.responses import (
    ContentInfoResponse, ProxyResponse, ProxyStatsResponse
)


class IConfig(ABC):
    """Интерфейс конфигурации"""

    @property
    @abstractmethod
    def log_level(self) -> str: ...

    @property
    @abstractmethod
    def timeout_connect(self) -> float: ...

    @property
    @abstractmethod
    def timeout_read(self) -> float: ...

    @property
    @abstractmethod
    def timeout_write(self) -> float: ...

    @property
    @abstractmethod
    def timeout_pool(self) -> float: ...

    @property
    @abstractmethod
    def use_proxy(self) -> bool: ...

    @property
    @abstractmethod
    def user_agent(self) -> str: ...

    @property
    @abstractmethod
    def max_redirects(self) -> int: ...

    @property
    @abstractmethod
    def stream_chunk_size(self) -> int: ...

    @property
    @abstractmethod
    def max_range_size(self) -> int: ...

    @property
    @abstractmethod
    def video_indicators(self) -> List[str]: ...

    @property
    @abstractmethod
    def video_extensions(self) -> List[str]: ...

    @property
    @abstractmethod
    def video_patterns(self) -> List[str]: ...

    @property
    @abstractmethod
    def proxy_list(self) -> List[str]: ...


class ITimeoutConfigurator(ABC):
    """Интерфейс конфигуратора таймаутов"""

    @abstractmethod
    def create_timeout_config(self, timeout_multiplier: int = 1) -> httpx.Timeout: ...


class IProxyManager(ABC):
    """Интерфейс менеджера прокси"""

    @abstractmethod
    async def validate_proxies(self, proxy_list: List[str]) -> List[str]: ...

    @abstractmethod
    async def add_proxy(self, proxy: str) -> bool: ...

    @abstractmethod
    def get_random_proxy(self) -> Optional[str]: ...

    @abstractmethod
    async def mark_proxy_success(self, proxy: str): ...

    @abstractmethod
    async def mark_proxy_failure(self, proxy: str): ...

    @abstractmethod
    def get_stats(self) -> ProxyStatsResponse: ...

    @property
    @abstractmethod
    def working_proxies(self) -> List[str]: ...

    @property
    @abstractmethod
    def proxy_stats(self) -> Dict[str, Dict[str, int]]: ...


class IProxyGenerator(ABC):
    """Интерфейс генератора прокси"""

    @abstractmethod
    async def get_proxy(self) -> Optional[str]: ...

    @abstractmethod
    async def mark_success(self, proxy: str): ...

    @abstractmethod
    async def mark_failure(self, proxy: str): ...

    @abstractmethod
    def has_proxies(self) -> bool: ...


class IHttpClientFactory(ABC):
    """Интерфейс фабрики HTTP клиентов"""

    @abstractmethod
    async def create_client(self,
                          headers: Dict = None,
                          is_video: bool = False,
                          follow_redirects: bool = True,
                          verify_ssl: bool = False,
                          proxy: str = None,
                          timeout: httpx.Timeout = None) -> AsyncGenerator[httpx.AsyncClient, None]: ...

    @abstractmethod
    async def cleanup(self): ...


class IContentInfoGetter(ABC):
    """Интерфейс получения информации о контенте"""

    @abstractmethod
    async def get_content_info(self, url: str, headers: Dict = None, use_head: bool = True) -> ContentInfoResponse: ...


class IVideoStreamerProcessor(ABC):
    """Интерфейс потоковой передачи видео"""

    @abstractmethod
    async def stream_video(self,
                         target_url: str,
                         request_headers: Dict,
                         range_header: str = None) -> StreamingResponse: ...


class IRequestProcessor(ABC):
    """Интерфейс обработчика запросов"""

    @abstractmethod
    async def process_request(self,
                           target_url: str,
                           method: str = 'GET',
                           data: Any = None,
                           headers: Dict = None) -> AsyncGenerator[ProxyResponse, None]: ...


class Im3u8Processor(ABC):
    """Интерфейс обработчика запросов"""

    @abstractmethod
    async def process_request(self,
                           target_url: str,
                           method: str = 'GET',
                           data: Any = None,
                           headers: Dict = None) -> AsyncGenerator[ProxyResponse, None]: ...


class IContentProcessor(ABC):
    """Интерфейс процессора контента"""

    @abstractmethod
    async def process_content(self,
                           target_url: str,
                           method: str = 'GET',
                           data: Any = None,
                           headers: Dict = None,
                           range_header: str = None) -> Any: ...


class IRouter(ABC):
    """Интерфейс роутера"""

    @abstractmethod
    def setup_routes(self, app): ...
