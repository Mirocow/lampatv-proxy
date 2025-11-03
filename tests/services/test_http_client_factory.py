import pytest
import httpx
from unittest.mock import Mock, AsyncMock, patch, call
from typing import Dict

from src.models.interfaces import IConfig, ITimeoutConfigurator
from src.services.http_client_factory import HttpClientFactory


class TestHttpClientFactory:
    """Тесты для HttpClientFactory"""

    @pytest.fixture
    def mock_dependencies(self):
        """Создает моки всех зависимостей"""
        config = Mock(spec=IConfig)
        timeout_configurator = Mock(spec=ITimeoutConfigurator)

        return {
            'config': config,
            'timeout_configurator': timeout_configurator
        }

    @pytest.fixture
    def http_client_factory(self, mock_dependencies):
        """Создает экземпляр HttpClientFactory с моками зависимостей"""
        return HttpClientFactory(**mock_dependencies)

    @pytest.mark.asyncio
    async def test_create_client_default_params(self, http_client_factory, mock_dependencies):
        """Тест создания клиента с параметрами по умолчанию"""
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client) as mock_client_class:
            async with http_client_factory.create_client() as client:
                pass

        mock_dependencies['timeout_configurator'].create_timeout_config.assert_called_once()
        mock_client_class.assert_called_once_with(
            headers={},
            timeout=default_timeout,
            follow_redirects=True,
            verify=False
        )

    @pytest.mark.asyncio
    async def test_create_client_with_custom_headers(self, http_client_factory, mock_dependencies):
        """Тест создания клиента с кастомными headers"""
        headers = {"User-Agent": "test-agent", "Accept": "application/json"}
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client) as mock_client_class:
            async with http_client_factory.create_client(headers=headers) as client:
                pass

        mock_client_class.assert_called_with(
            headers=headers.copy(),
            timeout=default_timeout,
            follow_redirects=True,
            verify=False
        )

    @pytest.mark.asyncio
    async def test_create_client_with_proxy(self, http_client_factory, mock_dependencies, caplog):
        """Тест создания клиента с прокси"""
        proxy_url = "http://proxy.example.com:8080"
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client) as mock_client_class:
            with caplog.at_level('INFO'):
                async with http_client_factory.create_client(proxy=proxy_url) as client:
                    pass

        mock_client_class.assert_called_with(
            headers={},
            timeout=default_timeout,
            follow_redirects=True,
            verify=False,
            proxy=proxy_url
        )
        assert f"Using specified proxy: {proxy_url}" in caplog.text

    @pytest.mark.asyncio
    async def test_create_client_with_custom_timeout(self, http_client_factory, mock_dependencies):
        """Тест создания клиента с кастомным timeout"""
        custom_timeout = Mock(spec=httpx.Timeout)

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client) as mock_client_class:
            async with http_client_factory.create_client(timeout=custom_timeout) as client:
                pass

        mock_dependencies['timeout_configurator'].create_timeout_config.assert_not_called()
        mock_client_class.assert_called_with(
            headers={},
            timeout=custom_timeout,
            follow_redirects=True,
            verify=False
        )

    @pytest.mark.asyncio
    async def test_create_client_with_ssl_verification(self, http_client_factory, mock_dependencies):
        """Тест создания клиента с проверкой SSL"""
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client) as mock_client_class:
            async with http_client_factory.create_client(verify_ssl=True) as client:
                pass

        mock_client_class.assert_called_with(
            headers={},
            timeout=default_timeout,
            follow_redirects=True,
            verify=True
        )

    @pytest.mark.asyncio
    async def test_create_client_without_redirects(self, http_client_factory, mock_dependencies):
        """Тест создания клиента без следования редиректам"""
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client) as mock_client_class:
            async with http_client_factory.create_client(follow_redirects=False) as client:
                pass

        mock_client_class.assert_called_with(
            headers={},
            timeout=default_timeout,
            follow_redirects=False,
            verify=False
        )

    @pytest.mark.asyncio
    async def test_create_client_for_video_content(self, http_client_factory, mock_dependencies):
        """Тест создания клиента для видео контента"""
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client) as mock_client_class:
            async with http_client_factory.create_client(is_video=True) as client:
                pass

        mock_client_class.assert_called_with(
            headers={},
            timeout=default_timeout,
            follow_redirects=True,
            verify=False
        )

    @pytest.mark.asyncio
    async def test_create_client_closes_on_exit(self, http_client_factory, mock_dependencies):
        """Тест что клиент закрывается при выходе из контекста"""
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client):
            async with http_client_factory.create_client() as client:
                pass

        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_client_closes_on_exception(self, http_client_factory, mock_dependencies):
        """Тест что клиент закрывается даже при исключении внутри контекста"""
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client):
            try:
                async with http_client_factory.create_client() as client:
                    raise ValueError("Test exception")
            except ValueError:
                pass

        mock_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_client_multiple_parameters_combination(self, http_client_factory, mock_dependencies):
        """Тест создания клиента с комбинацией различных параметров"""
        custom_timeout = Mock(spec=httpx.Timeout)
        headers = {"Authorization": "Bearer token"}
        proxy = "http://proxy:8080"

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client) as mock_client_class:
            async with http_client_factory.create_client(
                headers=headers,
                is_video=True,
                follow_redirects=False,
                verify_ssl=True,
                proxy=proxy,
                timeout=custom_timeout
            ) as client:
                pass

        mock_dependencies['timeout_configurator'].create_timeout_config.assert_not_called()
        mock_client_class.assert_called_with(
            headers=headers.copy(),
            timeout=custom_timeout,
            follow_redirects=False,
            verify=True,
            proxy=proxy
        )

    @pytest.mark.asyncio
    async def test_cleanup_empty_cache(self, http_client_factory):
        """Тест очистки пустого кэша"""
        await http_client_factory.cleanup()

    @pytest.mark.asyncio
    async def test_cleanup_with_clients(self, http_client_factory):
        """Тест очистки кэша с клиентами"""
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()

        http_client_factory._client_cache = {
            'client1': mock_client1,
            'client2': mock_client2
        }

        await http_client_factory.cleanup()

        mock_client1.aclose.assert_called_once()
        mock_client2.aclose.assert_called_once()
        assert http_client_factory._client_cache == {}

    @pytest.mark.asyncio
    async def test_cleanup_with_client_close_error(self, http_client_factory, caplog):
        """Тест очистки кэша когда закрытие клиента вызывает ошибку"""
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
        mock_client1.aclose.side_effect = Exception("Close error")

        http_client_factory._client_cache = {
            'client1': mock_client1,
            'client2': mock_client2
        }

        with caplog.at_level('WARNING'):
            await http_client_factory.cleanup()

        mock_client1.aclose.assert_called_once()
        mock_client2.aclose.assert_called_once()
        assert "Error closing cached client client1: Close error" in caplog.text
        assert http_client_factory._client_cache == {}

    @pytest.mark.asyncio
    async def test_create_client_headers_isolation(self, http_client_factory, mock_dependencies):
        """Тест что headers изолированы и не мутируют внешний объект"""
        original_headers = {"original": "header"}
        headers = original_headers.copy()

        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client) as mock_client_class:
            async with http_client_factory.create_client(headers=headers) as client:
                headers["modified"] = "true"

        call_kwargs = mock_client_class.call_args[1]
        assert call_kwargs['headers'] == {"original": "header"}

    def test_initialization(self, mock_dependencies):
        """Тест инициализации HttpClientFactory"""
        factory = HttpClientFactory(**mock_dependencies)

        assert factory.config == mock_dependencies['config']
        assert factory.timeout_configurator == mock_dependencies['timeout_configurator']
        assert factory.logger.name == 'lampa-proxy-http-factory'
        assert factory._client_cache == {}

    @pytest.mark.asyncio
    async def test_create_client_multiple_contexts(self, http_client_factory, mock_dependencies):
        """Тест создания нескольких клиентов в разных контекстах"""
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient') as mock_client_class:
            mock_client_class.side_effect = [mock_client1, mock_client2]

            async with http_client_factory.create_client() as client1:
                pass

            async with http_client_factory.create_client() as client2:
                pass

        assert mock_client_class.call_count == 2
        mock_client1.aclose.assert_called_once()
        mock_client2.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_client_with_none_headers(self, http_client_factory, mock_dependencies):
        """Тест создания клиента с явным None в headers"""
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client) as mock_client_class:
            async with http_client_factory.create_client(headers=None) as client:
                pass

        mock_client_class.assert_called_with(
            headers={},
            timeout=default_timeout,
            follow_redirects=True,
            verify=False
        )

    @pytest.mark.asyncio
    async def test_create_client_proxy_logging_only_when_proxy_present(self, http_client_factory, mock_dependencies, caplog):
        """Тест что логирование прокси происходит только когда прокси указан"""
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client):
            with caplog.at_level('INFO'):
                async with http_client_factory.create_client() as client:
                    pass

        assert "Using specified proxy:" not in caplog.text

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client):
            with caplog.at_level('INFO'):
                async with http_client_factory.create_client(proxy="http://proxy:8080") as client:
                    pass

        assert "Using specified proxy: http://proxy:8080" in caplog.text

    @pytest.mark.asyncio
    async def test_cleanup_logging(self, http_client_factory, caplog):
        """Тест логирования при очистке кэша"""
        mock_client = AsyncMock()
        http_client_factory._client_cache = {'test_client': mock_client}

        with caplog.at_level('DEBUG'):
            await http_client_factory.cleanup()

        assert "Closed cached client: test_client" in caplog.text

    @pytest.mark.asyncio
    async def test_create_client_real_usage_pattern(self, http_client_factory, mock_dependencies):
        """Тест реального паттерна использования клиента"""
        default_timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = default_timeout

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_client.get.return_value = mock_response

        with patch('src.services.http_client_factory.httpx.AsyncClient', return_value=mock_client):
            async with http_client_factory.create_client(
                headers={"User-Agent": "Test"},
                follow_redirects=False
            ) as client:
                response = await client.get("https://example.com")

        mock_client.get.assert_called_once_with("https://example.com")
        mock_client.aclose.assert_called_once()