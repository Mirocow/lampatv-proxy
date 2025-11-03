from src.models.interfaces import IConfig, IProxyManager, IProxyGenerator, IHttpClientFactory, IContentInfoGetter, IVideoStreamer, IRequestProcessor, IContentProcessor, IRouter, ITimeoutConfigurator
from src.config.app_config import AppConfig
from src.services.timeout_configurator import TimeoutConfigurator
from src.services.http_client_factory import HttpClientFactory
from src.services.proxy_manager import ProxyManager
from src.services.proxy_generator import DefaultProxyGenerator
from src.services.content_info_getter import ContentInfoGetter
from src.services.video_streamer import VideoStreamer
from src.services.request_processor import RequestProcessor
from src.services.content_processor import ContentProcessor
from src.services.request_handler import RequestHandler
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
        self._video_streamer = VideoStreamer(
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
        self._content_processor = ContentProcessor(
            self._config,
            self._http_factory,
            self._content_getter,
            self._video_streamer,
            self._request_processor
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
    def video_streamer(self) -> IVideoStreamer:
        return self._video_streamer

    @property
    def request_processor(self) -> IRequestProcessor:
        return self._request_processor

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
