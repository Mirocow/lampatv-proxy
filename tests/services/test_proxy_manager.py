import pytest
import httpx
import random
from unittest.mock import Mock, AsyncMock, patch, call
from typing import List, Dict

from src.models.interfaces import IHttpClientFactory, ITimeoutConfigurator
from src.models.responses import ProxyStatsResponse
from src.services.proxy_manager import ProxyManager


class TestProxyManager:
    """Тесты для ProxyManager"""

    @pytest.fixture
    def mock_dependencies(self):
        """Создает моки всех зависимостей"""
        http_factory = Mock(spec=IHttpClientFactory)
        timeout_configurator = Mock(spec=ITimeoutConfigurator)

        return {
            'http_factory': http_factory,
            'timeout_configurator': timeout_configurator
        }

    @pytest.fixture
    def proxy_manager(self, mock_dependencies):
        """Создает экземпляр ProxyManager с моками зависимостей"""
        return ProxyManager(**mock_dependencies)

    def test_initialization(self, mock_dependencies):
        """Тест инициализации ProxyManager"""
        # Act
        manager = ProxyManager(**mock_dependencies)

        # Assert
        assert manager.http_factory == mock_dependencies['http_factory']
        assert manager.timeout_configurator == mock_dependencies['timeout_configurator']
        assert manager._working_proxies == []
        assert manager._proxy_stats == {}
        assert manager.logger.name == 'lampa-proxy-manager'

    @pytest.mark.asyncio
    async def test_validate_proxies_empty_list(self, proxy_manager, caplog):
        """Тест валидации пустого списка прокси"""
        # Arrange
        proxy_list = []

        # Act
        with caplog.at_level('WARNING'):
            result = await proxy_manager.validate_proxies(proxy_list)

        # Assert
        assert result == []
        assert "No proxies provided for validation" in caplog.text

    @pytest.mark.asyncio
    async def test_validate_proxies_success(self, proxy_manager, mock_dependencies, caplog):
        """Тест успешной валидации прокси"""
        # Arrange
        proxy_list = ["proxy1:8080", "proxy2:8080", "proxy3:8080"]
        validation_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = validation_timeout

        # Мокируем test_proxy чтобы некоторые прокси прошли валидацию
        proxy_manager.test_proxy = AsyncMock(side_effect=[True, False, True])

        # Act
        with caplog.at_level('INFO'):
            result = await proxy_manager.validate_proxies(proxy_list)

        # Assert
        assert result == ["proxy1:8080", "proxy3:8080"]
        assert f"Starting validation of {len(proxy_list)} proxies..." in caplog.text
        assert "Proxy validation completed: 2/3 working" in caplog.text
        mock_dependencies['timeout_configurator'].create_timeout_config.assert_called_with(30.0)
        assert proxy_manager.test_proxy.call_count == 3

    @pytest.mark.asyncio
    async def test_validate_proxies_all_fail(self, proxy_manager, mock_dependencies, caplog):
        """Тест когда все прокси не прошли валидацию"""
        # Arrange
        proxy_list = ["proxy1:8080", "proxy2:8080"]
        validation_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = validation_timeout

        proxy_manager.test_proxy = AsyncMock(return_value=False)

        # Act
        with caplog.at_level('INFO'):
            result = await proxy_manager.validate_proxies(proxy_list)

        # Assert
        assert result == []
        assert "Proxy validation completed: 0/2 working" in caplog.text

    @pytest.mark.asyncio
    async def test_test_proxy_success(self, proxy_manager, mock_dependencies, caplog):
        """Тест успешного тестирования прокси"""
        # Arrange
        proxy = "192.168.1.1:8080"
        timeout = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {"ip": "192.168.1.1"}

        mock_client.get.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        with caplog.at_level('INFO'):
            result = await proxy_manager.test_proxy(proxy, timeout)

        # Assert
        assert result is True
        mock_dependencies['http_factory'].create_client.assert_called_with(
            proxy="http://192.168.1.1:8080",
            timeout=timeout,
            verify_ssl=False,
            follow_redirects=True
        )
        assert f"Testing proxy {proxy} with URL:" in caplog.text

    @pytest.mark.asyncio
    async def test_test_proxy_empty_proxy(self, proxy_manager, caplog):
        """Тест тестирования пустого прокси"""
        # Arrange
        proxy = ""

        # Act
        with caplog.at_level('DEBUG'):
            result = await proxy_manager.test_proxy(proxy)

        # Assert
        assert result is False
        assert "Empty proxy provided for testing" in caplog.text

    @pytest.mark.asyncio
    async def test_test_proxy_whitespace_proxy(self, proxy_manager):
        """Тест тестирования прокси из пробелов"""
        # Arrange
        proxy = "   "

        # Act
        result = await proxy_manager.test_proxy(proxy)

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_test_proxy_connection_error(self, proxy_manager, mock_dependencies, caplog):
        """Тест тестирования прокси с ошибкой соединения"""
        # Arrange
        proxy = "invalid-proxy:8080"
        timeout = Mock()

        mock_client = AsyncMock()
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = httpx.ConnectError("Connection failed")

        # Act
        with caplog.at_level('WARNING'):
            result = await proxy_manager.test_proxy(proxy, timeout)

        # Assert
        assert result is False
        assert f"✗ Proxy {proxy} connection error: Connection failed" in caplog.text

    @pytest.mark.asyncio
    async def test_test_proxy_timeout(self, proxy_manager, mock_dependencies, caplog):
        """Тест тестирования прокси с таймаутом"""
        # Arrange
        proxy = "slow-proxy:8080"
        timeout = Mock()

        mock_client = AsyncMock()
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")

        # Act
        with caplog.at_level('WARNING'):
            result = await proxy_manager.test_proxy(proxy, timeout)

        # Assert
        assert result is False
        assert f"✗ Proxy {proxy} timeout" in caplog.text

    @pytest.mark.asyncio
    async def test_test_proxy_all_urls_fail(self, proxy_manager, mock_dependencies, caplog):
        """Тест когда все тестовые URL не сработали"""
        # Arrange
        proxy = "failing-proxy:8080"
        timeout = Mock()

        mock_client = AsyncMock()
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = Exception("All URLs failed")

        # Act
        with caplog.at_level('WARNING'):
            result = await proxy_manager.test_proxy(proxy, timeout)

        # Assert
        assert result is False
        assert f"✗ Proxy {proxy} failed for all test URLs" in caplog.text

    @pytest.mark.asyncio
    async def test_test_proxy_non_200_status(self, proxy_manager, mock_dependencies, caplog):
        """Тест прокси возвращающего не 200 статус"""
        # Arrange
        proxy = "bad-status-proxy:8080"
        timeout = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 403
        mock_client.get.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        with caplog.at_level('WARNING'):
            result = await proxy_manager.test_proxy(proxy, timeout)

        # Assert
        assert result is False
        assert f"Proxy {proxy} returned status 403" in caplog.text

    def test_normalize_proxy_http(self, proxy_manager):
        """Тест нормализации HTTP прокси"""
        # Arrange
        test_cases = [
            ("192.168.1.1:8080", "http://192.168.1.1:8080"),
            ("http://proxy.com:8080", "http://proxy.com:8080"),
            ("  proxy.com:8080  ", "http://proxy.com:8080"),
        ]

        for input_proxy, expected in test_cases:
            # Act
            result = proxy_manager._normalize_proxy(input_proxy)

            # Assert
            assert result == expected

    def test_normalize_proxy_socks5(self, proxy_manager):
        """Тест нормализации SOCKS5 прокси"""
        # Arrange
        test_cases = [
            ("192.168.1.1:1080", "socks5://192.168.1.1:1080"),
            ("192.168.1.1:9050", "socks5://192.168.1.1:9050"),
            ("socks5://proxy.com:1080", "socks5://proxy.com:1080"),
        ]

        for input_proxy, expected in test_cases:
            # Act
            result = proxy_manager._normalize_proxy(input_proxy)

            # Assert
            assert result == expected

    @pytest.mark.asyncio
    async def test_add_proxy_success(self, proxy_manager, caplog):
        """Тест успешного добавления прокси"""
        # Arrange
        proxy = "new-proxy:8080"

        # Act
        with caplog.at_level('DEBUG'):
            result = await proxy_manager.add_proxy(proxy)

        # Assert
        assert result is True
        assert proxy in proxy_manager._working_proxies
        assert proxy in proxy_manager._proxy_stats
        assert proxy_manager._proxy_stats[proxy] == {'success': 0, 'failures': 0}
        assert f"Added proxy to working list: {proxy}" in caplog.text

    @pytest.mark.asyncio
    async def test_add_proxy_already_exists(self, proxy_manager, caplog):
        """Тест добавления уже существующего прокси"""
        # Arrange
        proxy = "existing-proxy:8080"
        await proxy_manager.add_proxy(proxy)

        # Act
        with caplog.at_level('DEBUG'):
            result = await proxy_manager.add_proxy(proxy)

        # Assert
        assert result is False
        assert proxy_manager._working_proxies.count(proxy) == 1
        assert f"Proxy already in working list: {proxy}" in caplog.text

    @pytest.mark.asyncio
    async def test_add_proxy_empty(self, proxy_manager, caplog):
        """Тест добавления пустого прокси"""
        # Arrange
        proxy = ""

        # Act
        with caplog.at_level('WARNING'):
            result = await proxy_manager.add_proxy(proxy)

        # Assert
        assert result is False
        assert "Attempted to add empty proxy" in caplog.text

    def test_get_random_proxy_with_proxies(self, proxy_manager):
        """Тест получения случайного прокси когда прокси есть"""
        # Arrange
        proxies = ["proxy1:8080", "proxy2:8080", "proxy3:8080"]
        proxy_manager._working_proxies = proxies

        with patch('random.choice') as mock_choice:
            mock_choice.return_value = "proxy2:8080"

            # Act
            result = proxy_manager.get_random_proxy()

        # Assert
        assert result == "proxy2:8080"
        mock_choice.assert_called_once_with(proxies)

    def test_get_random_proxy_no_proxies(self, proxy_manager, caplog):
        """Тест получения случайного прокси когда прокси нет"""
        # Arrange
        proxy_manager._working_proxies = []

        # Act
        with caplog.at_level('DEBUG'):
            result = proxy_manager.get_random_proxy()

        # Assert
        assert result is None
        assert "No working proxies available" in caplog.text

    def test_get_proxy_with_failover_no_proxies(self, proxy_manager):
        """Тест получения прокси с фейловером когда прокси нет"""
        # Arrange
        proxy_manager._working_proxies = []

        # Act
        result = proxy_manager.get_proxy_with_failover()

        # Assert
        assert result is None

    def test_get_proxy_with_failover_with_exclusions(self, proxy_manager, caplog):
        """Тест получения прокси с фейловером и исключениями"""
        # Arrange
        proxies = ["proxy1:8080", "proxy2:8080", "proxy3:8080"]
        excluded = ["proxy1:8080", "proxy3:8080"]
        proxy_manager._working_proxies = proxies

        # Настраиваем статистику для сортировки
        proxy_manager._proxy_stats = {
            "proxy1:8080": {"success": 10, "failures": 1},
            "proxy2:8080": {"success": 15, "failures": 2},  # Лучшая статистика
            "proxy3:8080": {"success": 5, "failures": 3},
        }

        # Act
        with caplog.at_level('DEBUG'):
            result = proxy_manager.get_proxy_with_failover(excluded_proxies=excluded)

        # Assert
        assert result == "proxy2:8080"
        assert f"Selected proxy with failover: proxy2:8080" in caplog.text

    def test_get_proxy_with_failover_all_excluded(self, proxy_manager, caplog):
        """Тест когда все прокси исключены"""
        # Arrange
        proxies = ["proxy1:8080", "proxy2:8080"]
        excluded = proxies.copy()
        proxy_manager._working_proxies = proxies

        # Act
        with caplog.at_level('WARNING'):
            result = proxy_manager.get_proxy_with_failover(excluded_proxies=excluded)

        # Assert
        assert result is None
        assert "No available proxies after failover exclusion" in caplog.text

    @pytest.mark.asyncio
    async def test_mark_proxy_success(self, proxy_manager, caplog):
        """Тест отметки успешного использования прокси"""
        # Arrange
        proxy = "proxy:8080"
        await proxy_manager.add_proxy(proxy)

        # Act
        with caplog.at_level('DEBUG'):
            await proxy_manager.mark_proxy_success(proxy)

        # Assert
        assert proxy_manager._proxy_stats[proxy]['success'] == 1
        assert f"Marked proxy success: {proxy} (successes: 1)" in caplog.text

    @pytest.mark.asyncio
    async def test_mark_proxy_success_not_found(self, proxy_manager):
        """Тест отметки успеха для несуществующего прокси"""
        # Arrange
        proxy = "unknown-proxy:8080"

        # Act
        await proxy_manager.mark_proxy_success(proxy)

        # Assert
        # Не должно быть исключения

    @pytest.mark.asyncio
    async def test_mark_proxy_failure(self, proxy_manager, caplog):
        """Тест отметки неудачного использования прокси"""
        # Arrange
        proxy = "proxy:8080"
        await proxy_manager.add_proxy(proxy)

        # Act
        with caplog.at_level('WARNING'):
            await proxy_manager.mark_proxy_failure(proxy)

        # Assert
        assert proxy_manager._proxy_stats[proxy]['failures'] == 1
        assert f"Marked proxy failure: {proxy} (failures: 1)" in caplog.text

    @pytest.mark.asyncio
    async def test_mark_proxy_failure_removal(self, proxy_manager, caplog):
        """Тест удаления прокси после множества неудач"""
        # Arrange
        proxy = "bad-proxy:8080"
        await proxy_manager.add_proxy(proxy)

        # Act - отмечаем 6 неудач (больше порога в 5)
        for i in range(6):
            await proxy_manager.mark_proxy_failure(proxy)

        # Assert
        assert proxy not in proxy_manager._working_proxies
        assert proxy not in proxy_manager._proxy_stats

    @pytest.mark.asyncio
    async def test_mark_proxy_failure_empty_proxy(self, proxy_manager):
        """Тест отметки неудачи для пустого прокси"""
        # Arrange
        proxy = ""

        # Act
        await proxy_manager.mark_proxy_failure(proxy)

        # Assert
        # Не должно быть исключения

    @pytest.mark.asyncio
    async def test_remove_proxy_success(self, proxy_manager, caplog):
        """Тест успешного удаления прокси"""
        # Arrange
        proxy = "proxy:8080"
        await proxy_manager.add_proxy(proxy)

        # Act
        with caplog.at_level('WARNING'):
            result = await proxy_manager.remove_proxy(proxy)

        # Assert
        assert result is True
        assert proxy not in proxy_manager._working_proxies
        assert proxy not in proxy_manager._proxy_stats
        assert f"Removed proxy from working list: {proxy}" in caplog.text

    @pytest.mark.asyncio
    async def test_remove_proxy_not_found(self, proxy_manager):
        """Тест удаления несуществующего прокси"""
        # Arrange
        proxy = "unknown-proxy:8080"

        # Act
        result = await proxy_manager.remove_proxy(proxy)

        # Assert
        assert result is False

    def test_get_stats(self, proxy_manager, caplog):
        """Тест получения статистики"""
        # Arrange
        proxy_manager._working_proxies = ["proxy1:8080", "proxy2:8080"]
        proxy_manager._proxy_stats = {
            "proxy1:8080": {"success": 10, "failures": 2},
            "proxy2:8080": {"success": 5, "failures": 1},
        }

        # Act
        with caplog.at_level('DEBUG'):
            result = proxy_manager.get_stats()

        # Assert
        assert isinstance(result, ProxyStatsResponse)
        assert result.total_working == 2
        assert result.total_success == 15
        assert result.total_failures == 3
        assert result.proxy_stats == proxy_manager._proxy_stats
        assert "Proxy stats: 2 working, 15 total successes, 3 total failures" in caplog.text

    def test_get_detailed_stats(self, proxy_manager):
        """Тест получения детальной статистики"""
        # Arrange
        proxy_manager._working_proxies = ["proxy1:8080", "proxy2:8080"]
        proxy_manager._proxy_stats = {
            "proxy1:8080": {"success": 10, "failures": 2},
            "proxy2:8080": {"success": 5, "failures": 1},
        }

        # Act
        result = proxy_manager.get_detailed_stats()

        # Assert
        assert result['total_working'] == 2
        assert result['total_success'] == 15
        assert result['total_failures'] == 3
        assert result['total_proxies_tested'] == 2
        assert result['success_rate'] == 15 / 18  # 15 успехов из 18 запросов

    def test_get_detailed_stats_zero_requests(self, proxy_manager):
        """Тест детальной статистики при нулевых запросах"""
        # Arrange
        proxy_manager._working_proxies = []
        proxy_manager._proxy_stats = {}

        # Act
        result = proxy_manager.get_detailed_stats()

        # Assert
        assert result['success_rate'] == 0

    def test_clear_stats(self, proxy_manager, caplog):
        """Тест очистки статистики"""
        # Arrange
        proxy_manager._proxy_stats = {
            "proxy1:8080": {"success": 10, "failures": 2},
            "proxy2:8080": {"success": 5, "failures": 1},
        }

        # Act
        with caplog.at_level('INFO'):
            proxy_manager.clear_stats()

        # Assert
        assert proxy_manager._proxy_stats == {}
        assert "Proxy statistics cleared" in caplog.text

    def test_len(self, proxy_manager):
        """Тест метода __len__"""
        # Arrange
        proxy_manager._working_proxies = ["proxy1:8080", "proxy2:8080"]

        # Act & Assert
        assert len(proxy_manager) == 2

    def test_bool_true(self, proxy_manager):
        """Тест метода __bool__ когда прокси есть"""
        # Arrange
        proxy_manager._working_proxies = ["proxy1:8080"]

        # Act & Assert
        assert bool(proxy_manager) is True

    def test_bool_false(self, proxy_manager):
        """Тест метода __bool__ когда прокси нет"""
        # Arrange
        proxy_manager._working_proxies = []

        # Act & Assert
        assert bool(proxy_manager) is False

    def test_str(self, proxy_manager):
        """Тест строкового представления"""
        # Arrange
        proxy_manager._working_proxies = ["proxy1:8080", "proxy2:8080"]

        # Act
        result = str(proxy_manager)

        # Assert
        assert result == "ProxyManager(working_proxies=2)"

    def test_repr(self, proxy_manager):
        """Тест представления для отладки"""
        # Arrange
        proxy_manager._working_proxies = ["proxy1:8080"]
        proxy_manager._proxy_stats = {"proxy1:8080": {"success": 1, "failures": 0}}

        # Act
        result = repr(proxy_manager)

        # Assert
        assert "ProxyManager" in result
        assert "working_proxies" in result
        assert "stats" in result

    def test_working_proxies_property(self, proxy_manager):
        """Тест свойства working_proxies"""
        # Arrange
        expected_proxies = ["proxy1:8080", "proxy2:8080"]
        proxy_manager._working_proxies = expected_proxies

        # Act & Assert
        assert proxy_manager.working_proxies == expected_proxies

    def test_proxy_stats_property(self, proxy_manager):
        """Тест свойства proxy_stats"""
        # Arrange
        expected_stats = {"proxy1:8080": {"success": 1, "failures": 0}}
        proxy_manager._proxy_stats = expected_stats

        # Act & Assert
        assert proxy_manager.proxy_stats == expected_stats

    @pytest.mark.asyncio
    async def test_test_proxy_with_json_response(self, proxy_manager, mock_dependencies, caplog):
        """Тест тестирования прокси с JSON ответом"""
        # Arrange
        proxy = "json-proxy:8080"
        timeout = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {"ip": "192.168.1.1"}

        mock_client.get.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        with caplog.at_level('INFO'):
            result = await proxy_manager.test_proxy(proxy, timeout)

        # Assert
        assert result is True
        assert "application/json" in caplog.text

    @pytest.mark.asyncio
    async def test_test_proxy_with_text_response(self, proxy_manager, mock_dependencies, caplog):
        """Тест тестирования прокси с текстовым ответом"""
        # Arrange
        proxy = "text-proxy:8080"
        timeout = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'text/plain'}
        mock_response.text = "192.168.1.1"

        mock_client.get.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        with caplog.at_level('INFO'):
            result = await proxy_manager.test_proxy(proxy, timeout)

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_test_proxy_success_first_url(self, proxy_manager, mock_dependencies):
        """Тест когда первый тестовый URL успешен"""
        # Arrange
        proxy = "working-proxy:8080"
        timeout = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'text/plain'}

        mock_client.get.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await proxy_manager.test_proxy(proxy, timeout)

        # Assert
        assert result is True
        # Должен быть только один вызов, так как первый URL успешен
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_initialization_logging(self, mock_dependencies, caplog):
        """Тест логирования при инициализации"""
        # Act
        with caplog.at_level('INFO'):
            ProxyManager(**mock_dependencies)

        # Assert
        assert "ProxyManager initialized with HttpClientFactory" in caplog.text