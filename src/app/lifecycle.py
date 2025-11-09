from src.utils.logger import get_logger


class ApplicationLifecycle:
    """Управление жизненным циклом приложения"""

    def __init__(self, container, application):
        self.container = container
        self.application = application
        self.logger = get_logger('lifecycle')

    async def startup(self):
        """Запуск приложения"""
        self.logger.info("Starting Lampa Proxy Server...")

        if self.container.config.use_proxy and self.container.config.proxy_list:
            self.logger.info("Starting proxy validation...")
            working_proxies = await self.container.proxy_manager.validate_proxies(self.container.config.proxy_list)

            for proxy in working_proxies:
                await self.container.proxy_manager.add_proxy(proxy)

            self.logger.info(f"Loaded {len(working_proxies)} working proxies")

        self.logger.info("Lampa Proxy Server started successfully")

    async def shutdown(self):
        """Завершение работы приложения"""
        self.logger.info("Shutting down Lampa Proxy Server...")
        await self.container.http_factory.cleanup()
        self.logger.info("HTTP client factory cleaned up")
        self.logger.info("Lampa Proxy Server shutdown completed")

