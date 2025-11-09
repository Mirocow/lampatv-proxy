from src.models.interfaces import IConfig, IProxyManager, IProxyGenerator, IHttpClientFactory, IContentInfoGetter, IVideoStreamerProcessor, IRequestProcessor, IContentProcessor, IRouter, ITimeoutConfigurator, Im3u8Processor
from src.config.app_config import AppConfig
from src.services.utils.timeout_configurator import TimeoutConfigurator
from src.services.utils.http_client_factory import HttpClientFactory
from src.services.proxy.proxy_manager import ProxyManager
from src.services.proxy.proxy_generator import DefaultProxyGenerator
from src.services.utils.content_info_getter import ContentInfoGetter
from src.services.processors.video_streamer_processor import VideoStreamerProcessor
from src.services.processors.request_processor import RequestProcessor
from src.services.processors.content_processor import ContentProcessor
from src.services.processors.m3u8_processor import M3U8Processor
from src.services.handlers.request_handler import RequestHandler
from src.routes.app_router import AppRouter


class DIContainer:
    """Контейнер зависимостей"""

    def __init__(self):
        self._config = AppConfig()
        self._timeout_configurator = TimeoutConfigurator(self._config)

        # Создаем клиент для запросов
        self._http_factory = HttpClientFactory(
            self._config,
            self._timeout_configurator
        )

        # Создаем ProxyManager с зависимостями
        self._proxy_manager = ProxyManager(
            self._config,
            self._http_factory,
            self._timeout_configurator
        )
        self._proxy_generator = DefaultProxyGenerator(
            self._proxy_manager,
            self._config
        )

        # Создаем зависимости с правильным порядком
        self._content_getter = ContentInfoGetter(
            self._config,
            self._http_factory,
            self._proxy_generator,
            self._timeout_configurator
        )
        self._video_streamer = VideoStreamerProcessor(
            self._config,
            self._http_factory,
            self._content_getter,
            self._proxy_generator,
            self._timeout_configurator
        )
        self._request_processor = RequestProcessor(
            self._config,
            self._http_factory,
            self._proxy_generator,
            self._timeout_configurator
        )
        self._m3u8_processor = M3U8Processor(
            self._config,
            self._http_factory,
            self._proxy_generator,
            self._timeout_configurator,
            self._request_processor,
        )
        self._content_processor = ContentProcessor(
            self._config,
            self._http_factory,
            self._content_getter,
            self._video_streamer,
            self._request_processor,
            self._m3u8_processor
        )

        # Создаем обработчик запросов
        self._request_handler = RequestHandler(self._content_processor, self._config)

        # Создаем роутер
        self._router = AppRouter(
            self._request_handler,
            self._content_processor,
            self._http_factory,
            self._proxy_manager,
            self._config
        )

    @property
    def config(self) -> IConfig:
        return self._config

    @property
    def proxy_manager(self) -> IProxyManager:
        return self._proxy_manager

    @property
    def proxy_generator(self) -> IProxyGenerator:
        return self._proxy_generator

    @property
    def http_factory(self) -> IHttpClientFactory:
        return self._http_factory

    @property
    def content_getter(self) -> IContentInfoGetter:
        return self._content_getter

    @property
    def video_streamer(self) -> IVideoStreamerProcessor:
        return self._video_streamer

    @property
    def request_processor(self) -> IRequestProcessor:
        return self._request_processor

    @property
    def m3u8_processor(self) -> Im3u8Processor:
        return self._m3u8_processor

    @property
    def content_processor(self) -> IContentProcessor:
        return self._content_processor

    @property
    def request_handler(self) -> RequestHandler:
        return self._request_handler

    @property
    def router(self) -> IRouter:
        return self._router

    @property
    def timeout_configurator(self) -> ITimeoutConfigurator:
        return self._timeout_configurator
