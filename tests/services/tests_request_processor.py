import pytest
import httpx
import urllib.parse
from unittest.mock import Mock, AsyncMock, patch, call
from typing import Dict, Any, AsyncGenerator

from src.models.interfaces import IConfig, IHttpClientFactory, IProxyGenerator, ITimeoutConfigurator
from src.models.responses import ProxyResponse
from src.services.request_processor import RequestProcessor


class TestRequestProcessor:
    """Тесты для RequestProcessor"""

    @pytest.fixture
    def mock_dependencies(self):
        """Создает моки всех зависимостей"""
        config = Mock(spec=IConfig)
        http_factory = Mock(spec=IHttpClientFactory)
        proxy_generator = Mock(spec=IProxyGenerator)
        timeout_configurator = Mock(spec=ITimeoutConfigurator)

        # Настройка конфигурации по умолчанию
        config.user_agent = "test-user-agent"
        config.max_redirects = 5

        return {
            'config': config,
            'http_factory': http_factory,
            'proxy_generator': proxy_generator,
            'timeout_configurator': timeout_configurator
        }

    @pytest.fixture
    def request_processor(self, mock_dependencies):
        """Создает экземпляр RequestProcessor с моками зависимостей"""
        return RequestProcessor(**mock_dependencies)

    def test_initialization(self, mock_dependencies):
        """Тест инициализации RequestProcessor"""
        # Act
        processor = RequestProcessor(**mock_dependencies)

        # Assert
        assert processor.config == mock_dependencies['config']
        assert processor.http_factory == mock_dependencies['http_factory']
        assert processor.proxy_generator == mock_dependencies['proxy_generator']
        assert processor.timeout_configurator == mock_dependencies['timeout_configurator']
        assert processor.logger.name == 'lampa-proxy-request-processor'

    @pytest.mark.asyncio
    async def test_process_request_success_get(self, request_processor, mock_dependencies, caplog):
        """Тест успешного GET запроса"""
        # Arrange
        target_url = "https://example.com/api/data"
        method = "GET"

        # Мокируем прокси
        mock_dependencies['proxy_generator'].has_proxies.return_value = False

        # Мокируем таймаут
        timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = timeout

        # Мокируем HTTP клиент
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = target_url
        mock_response.text = '{"result": "success"}'
        mock_response.headers = httpx.Headers({
            'content-type': 'application/json',
            'set-cookie': 'session=abc123'
        })
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        results = []
        async for result in request_processor.process_request(target_url, method):
            results.append(result)

        # Assert
        assert len(results) == 1
        response = results[0]
        assert response.status == 200
        assert response.body == '{"result": "success"}'
        assert response.currentUrl == target_url
        assert 'set-cookie' in response.headers
        assert response.headers['set-cookie'] == ['session=abc123']

        mock_dependencies['http_factory'].create_client.assert_called_with(
            headers={
                'User-Agent': 'test-user-agent',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,ru;q=0.7',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            },
            is_video=False,
            follow_redirects=False,
            verify_ssl=False,
            proxy=None,
            timeout=timeout
        )
        mock_client.request.assert_called_with('GET', target_url)
        assert f"Processing {method} request to: {target_url}" in caplog.text
        assert "Response status: 200" in caplog.text

    @pytest.mark.asyncio
    async def test_process_request_success_with_proxy(self, request_processor, mock_dependencies):
        """Тест успешного запроса с прокси"""
        # Arrange
        target_url = "https://example.com/api/data"
        proxy_url = "http://proxy.example.com:8080"

        # Мокируем прокси
        mock_dependencies['proxy_generator'].has_proxies.return_value = True
        mock_dependencies['proxy_generator'].get_proxy.return_value = proxy_url

        # Мокируем таймаут
        timeout = Mock()
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = timeout

        # Мокируем HTTP клиент
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = target_url
        mock_response.text = 'response text'
        mock_response.headers = httpx.Headers({})
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        results = []
        async for result in request_processor.process_request(target_url):
            results.append(result)

        # Assert
        assert len(results) == 1
        mock_dependencies['proxy_generator'].mark_success.assert_called_with(proxy_url)
        mock_dependencies['timeout_configurator'].create_timeout_config.assert_called_with(10)
        mock_dependencies['http_factory'].create_client.assert_called_with(
            headers=Mock.ANY,
            is_video=False,
            follow_redirects=False,
            verify_ssl=False,
            proxy=proxy_url,
            timeout=timeout
        )

    @pytest.mark.asyncio
    async def test_process_request_with_custom_headers(self, request_processor, mock_dependencies):
        """Тест запроса с кастомными заголовками"""
        # Arrange
        target_url = "https://example.com/api/data"
        headers = {"Authorization": "Bearer token", "Custom-Header": "value"}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = target_url
        mock_response.text = 'response'
        mock_response.headers = httpx.Headers({})
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        async for _ in request_processor.process_request(target_url, headers=headers):
            pass

        # Assert
        call_headers = mock_dependencies['http_factory'].create_client.call_args[1]['headers']
        assert call_headers['User-Agent'] == 'test-user-agent'  # из конфига
        assert call_headers['Authorization'] == 'Bearer token'  # из кастомных headers
        assert call_headers['Custom-Header'] == 'value'  # из кастомных headers

    @pytest.mark.asyncio
    async def test_process_request_post_with_dict_data(self, request_processor, mock_dependencies):
        """Тест POST запроса с данными в виде словаря"""
        # Arrange
        target_url = "https://example.com/api/data"
        method = "POST"
        data = {"key": "value", "number": 123}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = target_url
        mock_response.text = 'response'
        mock_response.headers = httpx.Headers({})
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        async for _ in request_processor.process_request(target_url, method, data):
            pass

        # Assert
        mock_client.request.assert_called_with('POST', target_url, data=data)

    @pytest.mark.asyncio
    async def test_process_request_post_with_content_data(self, request_processor, mock_dependencies):
        """Тест POST запроса с данными в виде контента"""
        # Arrange
        target_url = "https://example.com/api/data"
        method = "POST"
        data = b"binary data content"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = target_url
        mock_response.text = 'response'
        mock_response.headers = httpx.Headers({})
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        async for _ in request_processor.process_request(target_url, method, data):
            pass

        # Assert
        mock_client.request.assert_called_with('POST', target_url, content=data)

    @pytest.mark.asyncio
    async def test_process_request_redirect(self, request_processor, mock_dependencies, caplog):
        """Тест обработки редиректа"""
        # Arrange
        target_url = "https://example.com/old"
        redirect_url = "https://example.com/new"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        # Первый ответ с редиректом
        mock_client1 = AsyncMock()
        mock_response1 = Mock()
        mock_response1.status_code = 302
        mock_response1.headers = httpx.Headers({'location': redirect_url})
        mock_response1.url = target_url
        mock_client1.request.return_value = mock_response1

        # Второй ответ (после редиректа)
        mock_client2 = AsyncMock()
        mock_response2 = Mock()
        mock_response2.status_code = 200
        mock_response2.url = redirect_url
        mock_response2.text = 'final response'
        mock_response2.headers = httpx.Headers({})
        mock_client2.request.return_value = mock_response2

        # Чередуем клиенты
        mock_dependencies['http_factory'].create_client.side_effect = [
            mock_client1.__aenter__.return_value,
            mock_client2.__aenter__.return_value
        ]

        # Act
        results = []
        async for result in request_processor.process_request(target_url):
            results.append(result)

        # Assert
        assert len(results) == 1
        assert results[0].status == 200
        assert results[0].currentUrl == redirect_url
        assert "Following redirect 1 to: https://example.com/new" in caplog.text

    @pytest.mark.asyncio
    async def test_process_request_redirect_relative_url(self, request_processor, mock_dependencies):
        """Тест обработки редиректа с относительным URL"""
        # Arrange
        target_url = "https://example.com/old"
        redirect_url = "/new"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 302
        mock_response.headers = httpx.Headers({'location': redirect_url})
        mock_response.url = target_url
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Мокируем рекурсивный вызов process_request для абсолютного URL
        with patch.object(request_processor, 'process_request') as mock_process:
            mock_process.return_value = AsyncMock()
            mock_process.return_value.__aiter__.return_value = iter([ProxyResponse(
                currentUrl="https://example.com/new",
                cookie=[],
                headers={},
                status=200,
                body='response'
            )])

            # Act
            async for _ in request_processor.process_request(target_url):
                pass

            # Assert
            mock_process.assert_called_with("https://example.com/new", 'GET', None, Mock.ANY)

    @pytest.mark.asyncio
    async def test_process_request_too_many_redirects(self, request_processor, mock_dependencies):
        """Тест превышения максимального количества редиректов"""
        # Arrange
        target_url = "https://example.com/loop"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()
        mock_dependencies['config'].max_redirects = 2

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 302
        mock_response.headers = httpx.Headers({'location': 'https://example.com/loop2'})
        mock_response.url = target_url
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Мокируем рекурсивные вызовы до достижения лимита
        with patch.object(request_processor, 'process_request') as mock_process:
            # Симулируем слишком много редиректов
            mock_process.side_effect = ValueError("Too many redirects (max: 2)")

            # Act & Assert
            with pytest.raises(ValueError, match="Too many redirects"):
                async for _ in request_processor.process_request(target_url):
                    pass

    @pytest.mark.asyncio
    async def test_process_request_redirect_without_location(self, request_processor, mock_dependencies):
        """Тест редиректа без заголовка Location"""
        # Arrange
        target_url = "https://example.com/redirect"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 302
        mock_response.headers = httpx.Headers({})  # Нет location
        mock_response.url = target_url
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act & Assert
        with pytest.raises(ValueError, match="Redirect response without Location header"):
            async for _ in request_processor.process_request(target_url):
                pass

    @pytest.mark.asyncio
    async def test_process_request_timeout(self, request_processor, mock_dependencies, caplog):
        """Тест обработки таймаута"""
        # Arrange
        target_url = "https://example.com/slow"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_client.request.side_effect = httpx.TimeoutException("Request timed out")

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        results = []
        with caplog.at_level('ERROR'):
            async for result in request_processor.process_request(target_url):
                results.append(result)

        # Assert
        assert len(results) == 1
        response = results[0]
        assert response.status == 408
        assert response.error == 'Request timeout'
        assert f"✕ Request timeout: {target_url}" in caplog.text

    @pytest.mark.asyncio
    async def test_process_request_connection_error(self, request_processor, mock_dependencies, caplog):
        """Тест обработки ошибки соединения"""
        # Arrange
        target_url = "https://example.com/unreachable"
        proxy_url = "http://proxy.example.com:8080"

        mock_dependencies['proxy_generator'].has_proxies.return_value = True
        mock_dependencies['proxy_generator'].get_proxy.return_value = proxy_url
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_client.request.side_effect = httpx.RequestError("Connection failed")

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        results = []
        with caplog.at_level('ERROR'):
            async for result in request_processor.process_request(target_url):
                results.append(result)

        # Assert
        assert len(results) == 1
        response = results[0]
        assert response.status == 500
        assert 'Request failed' in response.error
        mock_dependencies['proxy_generator'].mark_failure.assert_called_with(proxy_url)
        assert f"✕ Request failed: {target_url}" in caplog.text

    @pytest.mark.asyncio
    async def test_process_request_unexpected_error(self, request_processor, mock_dependencies, caplog):
        """Тест обработки неожиданной ошибки"""
        # Arrange
        target_url = "https://example.com/error"
        proxy_url = "http://proxy.example.com:8080"

        mock_dependencies['proxy_generator'].has_proxies.return_value = True
        mock_dependencies['proxy_generator'].get_proxy.return_value = proxy_url
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_client.request.side_effect = ValueError("Unexpected error")

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        results = []
        with caplog.at_level('ERROR'):
            async for result in request_processor.process_request(target_url):
                results.append(result)

        # Assert
        assert len(results) == 1
        response = results[0]
        assert response.status == 500
        assert 'Unexpected error' in response.error
        mock_dependencies['proxy_generator'].mark_failure.assert_called_with(proxy_url)
        assert f"✕ Unexpected error: {target_url}" in caplog.text

    @pytest.mark.asyncio
    async def test_process_request_invalid_url_no_hostname(self, request_processor, caplog):
        """Тест запроса с невалидным URL без hostname"""
        # Arrange
        target_url = "invalid-url"

        # Act
        results = []
        with caplog.at_level('ERROR'):
            async for result in request_processor.process_request(target_url):
                results.append(result)

        # Assert
        assert len(results) == 1
        response = results[0]
        assert response.status == 500
        assert 'Unexpected error' in response.error

    @pytest.mark.asyncio
    async def test_process_request_empty_url(self, request_processor, caplog):
        """Тест запроса с пустым URL"""
        # Arrange
        target_url = ""

        # Act
        results = []
        with caplog.at_level('ERROR'):
            async for result in request_processor.process_request(target_url):
                results.append(result)

        # Assert
        assert len(results) == 1
        response = results[0]
        assert response.status == 500
        assert 'Unexpected error' in response.error

    def test_normalize_url_duplicate_protocol(self, request_processor, caplog):
        """Тест нормализации URL с дублирующимся протоколом"""
        # Arrange
        test_cases = [
            ("https://http://example.com", "https://example.com"),
            ("http://https://example.com", "http://example.com"),
            ("https://https://example.com", "https://example.com"),
        ]

        for input_url, expected in test_cases:
            # Act
            with caplog.at_level('DEBUG'):
                result = request_processor._normalize_url(input_url)

            # Assert
            assert result == expected
            assert "Removed duplicate protocol" in caplog.text

    def test_normalize_url_protocol_relative(self, request_processor, caplog):
        """Тест нормализации protocol-relative URL"""
        # Arrange
        url = "//example.com/path"

        # Act
        with caplog.at_level('DEBUG'):
            result = request_processor._normalize_url(url)

        # Assert
        assert result == "https://example.com/path"
        assert "Fixed protocol-relative URL" in caplog.text

    def test_normalize_url_missing_slash(self, request_processor, caplog):
        """Тест нормализации URL с отсутствующим слэшем"""
        # Arrange
        url = "https:/example.com"

        # Act
        with caplog.at_level('DEBUG'):
            result = request_processor._normalize_url(url)

        # Assert
        assert result == "https://example.com"
        assert "Normalized URL: https://example.com" in caplog.text

    def test_normalize_url_no_protocol(self, request_processor, caplog):
        """Тест нормализации URL без протокола"""
        # Arrange
        url = "example.com/path"

        # Act
        with caplog.at_level('DEBUG'):
            result = request_processor._normalize_url(url)

        # Assert
        assert result == "https://example.com/path"

    def test_normalize_url_already_normalized(self, request_processor, caplog):
        """Тест нормализации уже нормализованного URL"""
        # Arrange
        url = "https://example.com/path"

        # Act
        with caplog.at_level('DEBUG'):
            result = request_processor._normalize_url(url)

        # Assert
        assert result == "https://example.com/path"

    def test_normalize_url_empty_url(self, request_processor):
        """Тест нормализации пустого URL"""
        # Arrange
        url = ""

        # Act & Assert
        with pytest.raises(ValueError, match="Empty URL"):
            request_processor._normalize_url(url)

    @pytest.mark.asyncio
    async def test_process_request_put_method(self, request_processor, mock_dependencies):
        """Тест PUT запроса"""
        # Arrange
        target_url = "https://example.com/api/resource"
        method = "PUT"
        data = {"key": "value"}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = target_url
        mock_response.text = 'updated'
        mock_response.headers = httpx.Headers({})
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        async for _ in request_processor.process_request(target_url, method, data):
            pass

        # Assert
        mock_client.request.assert_called_with('PUT', target_url, data=data)

    @pytest.mark.asyncio
    async def test_process_request_delete_method(self, request_processor, mock_dependencies):
        """Тест DELETE запроса"""
        # Arrange
        target_url = "https://example.com/api/resource/123"
        method = "DELETE"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.url = target_url
        mock_response.text = ''
        mock_response.headers = httpx.Headers({})
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        async for _ in request_processor.process_request(target_url, method):
            pass

        # Assert
        mock_client.request.assert_called_with('DELETE', target_url)

    @pytest.mark.asyncio
    async def test_process_request_multiple_cookies(self, request_processor, mock_dependencies):
        """Тест обработки множественных cookies"""
        # Arrange
        target_url = "https://example.com/api/data"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = target_url
        mock_response.text = 'response'
        mock_response.headers = httpx.Headers({
            'set-cookie': ['session=abc123', 'user=john'],
            'content-type': 'application/json'
        })
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        results = []
        async for result in request_processor.process_request(target_url):
            results.append(result)

        # Assert
        assert len(results) == 1
        response = results[0]
        assert response.headers['set-cookie'] == ['session=abc123', 'user=john']
        assert response.cookie == ['session=abc123', 'user=john']

    @pytest.mark.asyncio
    async def test_process_request_case_insensitive_headers(self, request_processor, mock_dependencies):
        """Тест case-insensitive обработки заголовков"""
        # Arrange
        target_url = "https://example.com/api/data"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = target_url
        mock_response.text = 'response'
        mock_response.headers = httpx.Headers({
            'Set-Cookie': 'session=abc123',
            'Content-Type': 'application/json'
        })
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        results = []
        async for result in request_processor.process_request(target_url):
            results.append(result)

        # Assert
        assert len(results) == 1
        response = results[0]
        assert 'set-cookie' in response.headers
        assert 'content-type' in response.headers

    @pytest.mark.asyncio
    async def test_process_request_default_headers(self, request_processor, mock_dependencies):
        """Тест что заголовки по умолчанию устанавливаются правильно"""
        # Arrange
        target_url = "https://example.com/api/data"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.url = target_url
        mock_response.text = 'response'
        mock_response.headers = httpx.Headers({})
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act - без передачи headers
        async for _ in request_processor.process_request(target_url):
            pass

        # Assert
        call_headers = mock_dependencies['http_factory'].create_client.call_args[1]['headers']
        expected_defaults = {
            'User-Agent': 'test-user-agent',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,ru;q=0.7',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }
        for key, value in expected_defaults.items():
            assert call_headers[key] == value

    @pytest.mark.asyncio
    async def test_handle_redirect_with_post_data(self, request_processor, mock_dependencies):
        """Тест обработки редиректа с POST данными"""
        # Arrange
        target_url = "https://example.com/old"
        redirect_url = "https://example.com/new"
        method = "POST"
        data = {"key": "value"}
        headers = {"Content-Type": "application/json"}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 307  # Temporary Redirect (сохраняет метод)
        mock_response.headers = httpx.Headers({'location': redirect_url})
        mock_response.url = target_url
        mock_client.request.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Мокируем рекурсивный вызов
        with patch.object(request_processor, 'process_request') as mock_process:
            mock_process.return_value = AsyncMock()
            mock_process.return_value.__aiter__.return_value = iter([ProxyResponse(
                currentUrl=redirect_url,
                cookie=[],
                headers={},
                status=200,
                body='response'
            )])

            # Act
            async for _ in request_processor.process_request(target_url, method, data, headers):
                pass

            # Assert
            mock_process.assert_called_with(redirect_url, method, data, headers)