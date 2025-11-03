from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.__init__ import __name__, __description__, __version__
from src.di.container import DIContainer


class Application:
    """Основной класс приложения"""

    def __init__(self, container: DIContainer):
        self.container = container
        self.app = self._create_fastapi_app()
        self._setup_middleware()
        self._setup_router()

    def _create_fastapi_app(self) -> FastAPI:
        return FastAPI(
            title=__name__,
            description=__description__,
            version=__version__
        )

    def _setup_middleware(self):
        """Настройка middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _setup_router(self):
        """Настройка маршрутов через роутер"""
        self.container.router.setup_routes(self.app)