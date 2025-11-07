import logging
import random
from typing import List, Dict, Optional

import httpx

from src.models.interfaces import IHttpClientFactory, ITimeoutConfigurator, IProxyManager
from src.models.responses import ProxyStatsResponse


class ProxyManager(IProxyManager):
    """
    Менеджер для работы с прокси
    """

    def __init__(self, http_factory: IHttpClientFactory, timeout_configurator: ITimeoutConfigurator):
        self.http_factory = http_factory
        self.timeout_configurator = timeout_configurator
        self._working_proxies: List[str] = []
        self._proxy_stats: Dict[str, Dict[str, int]] = {}
        self.logger = logging.getLogger('lampa-proxy-manager')
        self.logger.info("ProxyManager initialized with HttpClientFactory")

    async def validate_proxies(self, proxy_list: List[str]) -> List[str]:
        """
        Валидация списка прокси
        """
        if not proxy_list:
            self.logger.warning("No proxies provided for validation")
            return []

        working_proxies = []
        self.logger.info(f"Starting validation of {len(proxy_list)} proxies...")

        # Создаем таймаут для валидации прокси
        validation_timeout = self.timeout_configurator.create_timeout_config(30.0)

        for i, proxy in enumerate(proxy_list, 1):
            self.logger.debug(f"Testing proxy {i}/{len(proxy_list)}: {proxy}")
            if await self.test_proxy(proxy, validation_timeout):
                working_proxies.append(proxy)
                self.logger.info(f"✓ Proxy validated: {proxy}")
            else:
                self.logger.warning(f"✗ Proxy failed: {proxy}")

        self.logger.info(
            f"Proxy validation completed: {len(working_proxies)}/{len(proxy_list)} working")

        return working_proxies

    async def test_proxy(self, proxy: str, timeout: httpx.Timeout = None) -> bool:
        """
        Тестирование отдельного прокси
        """
        if not proxy or not proxy.strip():
            self.logger.debug("Empty proxy provided for testing")
            return False

        try:
            # Нормализуем формат прокси
            normalized_proxy = self._normalize_proxy(proxy)

            async with self.http_factory.create_client(
                proxy=normalized_proxy,
                timeout=timeout,
                verify_ssl=False,  # Отключаем проверку SSL для прокси
                follow_redirects=True
            ) as client:
                #response = await client.get("http://httpbin.org/ip")
                # Используем несколько тестовых URL
                test_urls = [
                    "https://ifconfig.me/ip",
                    "http://httpbin.org/ip",
                    "http://api.ipify.org?format=json"
                ]

                for test_url in test_urls:
                    try:
                        self.logger.info(f"Testing proxy {proxy} with URL: {test_url}")
                        response = await client.get(test_url)

                        if response.status_code == 200:
                            try:
                                response_content_type = response.headers.get('content-type', '').lower()
                                if 'application/json' in response_content_type:
                                    data = response.json()
                                else:
                                    data = response.read()

                                #self.logger.info(f"✓ Proxy {proxy} is working with {test_url},: {data}")

                            except:
                                self.logger.info(f"✗ Proxy test response text: {response.text[:200]}...")

                            return True

                        else:
                            self.logger.warning(f"Proxy {proxy} returned status {response.status_code} for {test_url}")

                    except Exception as e:
                        self.logger.warning(f"✗ Proxy {proxy} failed for {test_url}: {str(e)}")
                        continue

                # Если ни один URL не сработал
                self.logger.warning(f"✗ Proxy {proxy} failed for all test URLs")
                return False


        except httpx.ConnectError as e:
            self.logger.warning(f"✗ Proxy {proxy} connection error: {str(e)}")
            return False

        except httpx.TimeoutException:
            self.logger.warning(f"✗ Proxy {proxy} timeout")
            return False

        except Exception as e:
            self.logger.debug(f"Proxy test failed for {proxy}: {str(e)}")
            return False

    def _normalize_proxy(self, proxy: str) -> str:
        """
        Нормализация формата прокси
        """
        proxy = proxy.strip()

        # Добавляем схему если отсутствует
        if not proxy.startswith(('http://', 'https://', 'socks5://')):
            # Пробуем определить тип прокси по порту или добавляем http:// по умолчанию
            if ':1080' in proxy or ':9050' in proxy:
                proxy = f"socks5://{proxy}"
            else:
                proxy = f"http://{proxy}"

        return proxy

    async def add_proxy(self, proxy: str) -> bool:
        """
        Добавление прокси в рабочий список. Возвращает True если прокси добавлен
        """
        if not proxy:
            self.logger.warning("Attempted to add empty proxy")
            return False

        if proxy not in self._working_proxies:
            self._working_proxies.append(proxy)
            self._proxy_stats[proxy] = {'success': 0, 'failures': 0}
            self.logger.debug(f"Added proxy to working list: {proxy}")
            return True
        else:
            self.logger.debug(f"Proxy already in working list: {proxy}")
            return False

    def get_random_proxy(self) -> Optional[str]:
        """
        Получение случайного рабочего прокси
        """
        if not self._working_proxies:
            self.logger.debug("No working proxies available")
            return None

        proxy = random.choice(self._working_proxies)
        self.logger.debug(f"Selected random proxy: {proxy}")
        return proxy

    # def get_proxy_with_failover(self, excluded_proxies: List[str] = None) -> Optional[str]:
    #     """
    #     Получение прокси с исключением неудачных
    #     """
    #     if not self._working_proxies:
    #         return None

    #     available_proxies = self._working_proxies.copy()

    #     # Исключаем указанные прокси
    #     if excluded_proxies:
    #         available_proxies = [
    #             p for p in available_proxies if p not in excluded_proxies]

    #     if not available_proxies:
    #         self.logger.warning("No available proxies after failover exclusion")
    #         return None

    #     # Предпочитаем прокси с лучшей статистикой
    #     available_proxies.sort(
    #         key=lambda p: self._proxy_stats.get(p, {}).get('success', 0) -
    #         self._proxy_stats.get(p, {}).get('failures', 0),
    #         reverse=True
    #     )

    #     selected_proxy = available_proxies[0]
    #     self.logger.debug(f"Selected proxy with failover: {selected_proxy}")
    #     return selected_proxy

    async def mark_proxy_success(self, proxy: str):
        """
        Отметка успешного использования прокси
        """
        if proxy and proxy in self._proxy_stats:
            self._proxy_stats[proxy]['success'] += 1
            self.logger.debug(
                f"Marked proxy success: {proxy} (successes: {self._proxy_stats[proxy]['success']})")

    async def mark_proxy_failure(self, proxy: str):
        """
        Отметка неудачного использования прокси
        """
        if not proxy:
            return

        if proxy in self._proxy_stats:
            self._proxy_stats[proxy]['failures'] += 1
            failures = self._proxy_stats[proxy]['failures']
            self.logger.warning(f"Marked proxy failure: {proxy} (failures: {failures})")

            # Если слишком много ошибок, удаляем прокси
            if failures > 5:
                await self.remove_proxy(proxy)

    async def remove_proxy(self, proxy: str) -> bool:
        """
        Удаление прокси из рабочего списка. Возвращает True если прокси был удален
        """
        if proxy in self._working_proxies:
            self._working_proxies.remove(proxy)
            if proxy in self._proxy_stats:
                del self._proxy_stats[proxy]
            self.logger.warning(f"Removed proxy from working list: {proxy}")
            return True
        return False

    def get_stats(self) -> ProxyStatsResponse:
        """
        Получение статистики по прокси
        """
        total_success = sum(stats.get('success', 0) for stats in self._proxy_stats.values())
        total_failures = sum(stats.get('failures', 0) for stats in self._proxy_stats.values())

        self.logger.debug(
            f"Proxy stats: {len(self._working_proxies)} working, "
            f"{total_success} total successes, {total_failures} total failures"
        )

        return ProxyStatsResponse(
            total_working=len(self._working_proxies),
            proxy_stats=self._proxy_stats,
            total_success=total_success,
            total_failures=total_failures
        )

    # def get_detailed_stats(self) -> Dict:
    #     """
    #     Получение детальной статистики
    #     """
    #     stats = self.get_stats().dict()
    #     stats['total_proxies_tested'] = len(self._proxy_stats)

    #     total_requests = stats['total_success'] + stats['total_failures']
    #     stats['success_rate'] = (
    #         (stats['total_success'] / total_requests) if total_requests > 0 else 0
    #     )

    #     return stats

    # def clear_stats(self):
    #     """Очистка статистики"""
    #     self._proxy_stats.clear()
    #     self.logger.info("Proxy statistics cleared")

    def __len__(self) -> int:
        """Количество рабочих прокси"""
        return len(self._working_proxies)

    def __bool__(self) -> bool:
        """Есть ли рабочие прокси"""
        return len(self._working_proxies) > 0

    def __str__(self) -> str:
        """Строковое представление"""
        return f"ProxyManager(working_proxies={len(self._working_proxies)})"

    def __repr__(self) -> str:
        """Представление для отладки"""
        return f"ProxyManager(working_proxies={self._working_proxies}, stats={self._proxy_stats})"

    @property
    def working_proxies(self) -> List[str]:
        return self._working_proxies

    @property
    def proxy_stats(self) -> Dict[str, Dict[str, int]]:
        return self._proxy_stats
