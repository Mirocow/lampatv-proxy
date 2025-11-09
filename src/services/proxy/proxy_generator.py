from typing import Optional

from src.utils.logger import get_logger
from src.models.interfaces import IProxyGenerator, IProxyManager, IConfig


class DefaultProxyGenerator(IProxyGenerator):
    """Генератор прокси по умолчанию"""

    def __init__(self,
                 proxy_manager: IProxyManager,
                 config: IConfig):
        self.proxy_manager = proxy_manager
        self.config = config
        self.logger = get_logger('proxy-generator', self.config.log_level)

    async def get_proxy(self) -> Optional[str]:
        if not self.has_proxies():
            return None
        return self.proxy_manager.get_random_proxy()

    async def mark_success(self, proxy: str):
        await self.proxy_manager.mark_proxy_success(proxy)

    async def mark_failure(self, proxy: str):
        await self.proxy_manager.mark_proxy_failure(proxy)

    def has_proxies(self) -> bool:
        return (self.config.use_proxy and
                self.proxy_manager.working_proxies and
                len(self.proxy_manager.working_proxies) > 0)
