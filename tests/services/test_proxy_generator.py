import pytest
from unittest.mock import Mock, AsyncMock
from typing import Optional

from src.models.interfaces import IProxyManager, IConfig
from src.services.proxy_generator import DefaultProxyGenerator


class TestDefaultProxyGenerator:
    """Тесты для DefaultProxyGenerator"""

    @pytest.fixture
    def mock_dependencies(self):
        """Создает моки всех зависимостей"""
        proxy_manager = Mock(spec=IProxyManager)
        config = Mock(spec=IConfig)

        return {
            'proxy_manager': proxy_manager,
            'config': config
        }

    @pytest.fixture
    def proxy_generator(self, mock_dependencies):
        """Создает экземпляр DefaultProxyGenerator с моками зависимостей"""
        return DefaultProxyGenerator(**mock_dependencies)

    def test_initialization(self, mock_dependencies):
        """Тест инициализации DefaultProxyGenerator"""
        # Act
        generator = DefaultProxyGenerator(**mock_dependencies)

        # Assert
        assert generator.proxy_manager == mock_dependencies['proxy_manager']
        assert generator.config == mock_dependencies['config']
        assert generator.logger.name == 'lampa-proxy-generator'

    @pytest.mark.asyncio
    async def test_get_proxy_with_proxies_available(self, proxy_generator, mock_dependencies):
        """Тест получения прокси когда прокси доступны"""
        # Arrange
        expected_proxy = "http://proxy.example.com:8080"
        mock_dependencies['config'].use_proxy = True
        mock_dependencies['proxy_manager'].working_proxies = [expected_proxy, "http://proxy2.example.com:8080"]
        mock_dependencies['proxy_manager'].get_random_proxy.return_value = expected_proxy

        # Act
        result = await proxy_generator.get_proxy()

        # Assert
        assert result == expected_proxy
        mock_dependencies['proxy_manager'].get_random_proxy.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_proxy_when_no_proxies_available(self, proxy_generator, mock_dependencies):
        """Тест получения прокси когда прокси недоступны"""
        # Arrange
        mock_dependencies['config'].use_proxy = True
        mock_dependencies['proxy_manager'].working_proxies = []  # Пустой список

        # Act
        result = await proxy_generator.get_proxy()

        # Assert
        assert result is None
        mock_dependencies['proxy_manager'].get_random_proxy.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_proxy_when_use_proxy_false(self, proxy_generator, mock_dependencies):
        """Тест получения прокси когда use_proxy = False"""
        # Arrange
        mock_dependencies['config'].use_proxy = False
        mock_dependencies['proxy_manager'].working_proxies = ["http://proxy.example.com:8080"]  # Есть прокси, но use_proxy=False

        # Act
        result = await proxy_generator.get_proxy()

        # Assert
        assert result is None
        mock_dependencies['proxy_manager'].get_random_proxy.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_proxy_when_working_proxies_none(self, proxy_generator, mock_dependencies):
        """Тест получения прокси когда working_proxies = None"""
        # Arrange
        mock_dependencies['config'].use_proxy = True
        mock_dependencies['proxy_manager'].working_proxies = None  # None вместо списка

        # Act
        result = await proxy_generator.get_proxy()

        # Assert
        assert result is None
        mock_dependencies['proxy_manager'].get_random_proxy.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_success(self, proxy_generator, mock_dependencies):
        """Тест отметки успешного использования прокси"""
        # Arrange
        proxy = "http://proxy.example.com:8080"
        mock_dependencies['proxy_manager'].mark_proxy_success = AsyncMock()

        # Act
        await proxy_generator.mark_success(proxy)

        # Assert
        mock_dependencies['proxy_manager'].mark_proxy_success.assert_called_once_with(proxy)

    @pytest.mark.asyncio
    async def test_mark_failure(self, proxy_generator, mock_dependencies):
        """Тест отметки неудачного использования прокси"""
        # Arrange
        proxy = "http://proxy.example.com:8080"
        mock_dependencies['proxy_manager'].mark_proxy_failure = AsyncMock()

        # Act
        await proxy_generator.mark_failure(proxy)

        # Assert
        mock_dependencies['proxy_manager'].mark_proxy_failure.assert_called_once_with(proxy)

    def test_has_proxies_true(self, proxy_generator, mock_dependencies):
        """Тест has_proxies возвращает True при наличии прокси"""
        # Arrange
        mock_dependencies['config'].use_proxy = True
        mock_dependencies['proxy_manager'].working_proxies = ["proxy1", "proxy2"]

        # Act
        result = proxy_generator.has_proxies()

        # Assert
        assert result is True

    def test_has_proxies_false_when_use_proxy_false(self, proxy_generator, mock_dependencies):
        """Тест has_proxies возвращает False когда use_proxy = False"""
        # Arrange
        mock_dependencies['config'].use_proxy = False
        mock_dependencies['proxy_manager'].working_proxies = ["proxy1", "proxy2"]  # Есть прокси, но use_proxy=False

        # Act
        result = proxy_generator.has_proxies()

        # Assert
        assert result is False

    def test_has_proxies_false_when_no_working_proxies(self, proxy_generator, mock_dependencies):
        """Тест has_proxies возвращает False когда нет рабочих прокси"""
        # Arrange
        mock_dependencies['config'].use_proxy = True
        mock_dependencies['proxy_manager'].working_proxies = []  # Пустой список

        # Act
        result = proxy_generator.has_proxies()

        # Assert
        assert result is False

    def test_has_proxies_false_when_working_proxies_none(self, proxy_generator, mock_dependencies):
        """Тест has_proxies возвращает False когда working_proxies = None"""
        # Arrange
        mock_dependencies['config'].use_proxy = True
        mock_dependencies['proxy_manager'].working_proxies = None  # None вместо списка

        # Act
        result = proxy_generator.has_proxies()

        # Assert
        assert result is False

    def test_has_proxies_false_when_working_proxies_empty_but_use_proxy_true(self, proxy_generator, mock_dependencies):
        """Тест has_proxies возвращает False когда use_proxy=True но working_proxies пуст"""
        # Arrange
        mock_dependencies['config'].use_proxy = True
        mock_dependencies['proxy_manager'].working_proxies = []  # Пустой список при use_proxy=True

        # Act
        result = proxy_generator.has_proxies()

        # Assert
        assert result is False

    def test_has_proxies_edge_case_single_proxy(self, proxy_generator, mock_dependencies):
        """Тест has_proxies с одним прокси в списке"""
        # Arrange
        mock_dependencies['config'].use_proxy = True
        mock_dependencies['proxy_manager'].working_proxies = ["single_proxy"]  # Один элемент

        # Act
        result = proxy_generator.has_proxies()

        # Assert
        assert result is True

    @pytest.mark.asyncio
    async def test_get_proxy_integration_with_has_proxies(self, proxy_generator, mock_dependencies):
        """Интеграционный тест get_proxy с has_proxies"""
        # Arrange
        test_cases = [
            # (use_proxy, working_proxies, expected_result)
            (True, ["p1", "p2"], "p1"),
            (True, [], None),
            (True, None, None),
            (False, ["p1", "p2"], None),
            (False, [], None),
            (False, None, None),
        ]

        for use_proxy, working_proxies, expected in test_cases:
            mock_dependencies['config'].use_proxy = use_proxy
            mock_dependencies['proxy_manager'].working_proxies = working_proxies

            if working_proxies and len(working_proxies) > 0 and use_proxy:
                mock_dependencies['proxy_manager'].get_random_proxy.return_value = working_proxies[0]

            # Act
            result = await proxy_generator.get_proxy()

            # Assert
            assert result == expected, f"Failed for use_proxy={use_proxy}, working_proxies={working_proxies}"

    @pytest.mark.asyncio
    async def test_mark_success_with_async_manager(self, proxy_generator, mock_dependencies):
        """Тест mark_success с асинхронным менеджером прокси"""
        # Arrange
        proxy = "http://proxy.example.com:8080"

        # Создаем асинхронный мок
        async_mock = AsyncMock()
        mock_dependencies['proxy_manager'].mark_proxy_success = async_mock

        # Act
        await proxy_generator.mark_success(proxy)

        # Assert
        async_mock.assert_called_once_with(proxy)

    @pytest.mark.asyncio
    async def test_mark_failure_with_async_manager(self, proxy_generator, mock_dependencies):
        """Тест mark_failure с асинхронным менеджером прокси"""
        # Arrange
        proxy = "http://proxy.example.com:8080"

        # Создаем асинхронный мок
        async_mock = AsyncMock()
        mock_dependencies['proxy_manager'].mark_proxy_failure = async_mock

        # Act
        await proxy_generator.mark_failure(proxy)

        # Assert
        async_mock.assert_called_once_with(proxy)

    def test_has_proxies_with_different_collection_types(self, proxy_generator, mock_dependencies):
        """Тест has_proxies с различными типами коллекций"""
        # Arrange
        mock_dependencies['config'].use_proxy = True

        test_cases = [
            (["p1", "p2"], True),  # list
            (("p1", "p2"), True),  # tuple
            ({"p1", "p2"}, True),  # set
            ({"p1": "url1", "p2": "url2"}, True),  # dict (keys)
        ]

        for working_proxies, expected in test_cases:
            mock_dependencies['proxy_manager'].working_proxies = working_proxies

            # Act
            result = proxy_generator.has_proxies()

            # Assert
            assert result == expected, f"Failed for working_proxies type: {type(working_proxies)}"

    @pytest.mark.asyncio
    async def test_get_proxy_returns_none_when_has_proxies_false(self, proxy_generator, mock_dependencies):
        """Тест что get_proxy возвращает None когда has_proxies возвращает False"""
        # Arrange
        # Настроим так, чтобы has_proxies возвращал False
        mock_dependencies['config'].use_proxy = False
        mock_dependencies['proxy_manager'].working_proxies = ["proxy1", "proxy2"]

        # Act
        result = await proxy_generator.get_proxy()

        # Assert
        assert result is None
        mock_dependencies['proxy_manager'].get_random_proxy.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_proxy_calls_get_random_proxy_when_has_proxies_true(self, proxy_generator, mock_dependencies):
        """Тест что get_proxy вызывает get_random_proxy когда has_proxies возвращает True"""
        # Arrange
        expected_proxy = "http://proxy.example.com:8080"
        mock_dependencies['config'].use_proxy = True
        mock_dependencies['proxy_manager'].working_proxies = [expected_proxy]
        mock_dependencies['proxy_manager'].get_random_proxy.return_value = expected_proxy

        # Act
        result = await proxy_generator.get_proxy()

        # Assert
        assert result == expected_proxy
        mock_dependencies['proxy_manager'].get_random_proxy.assert_called_once()