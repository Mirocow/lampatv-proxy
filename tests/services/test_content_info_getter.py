import pytest
import httpx
from unittest.mock import Mock, AsyncMock, patch
from src.models.interfaces import IConfig, IHttpClientFactory, IProxyGenerator, ITimeoutConfigurator
from src.models.responses import ContentInfoResponse
from src.services.content_info_getter import ContentInfoGetter


class TestContentInfoGetter:
    """Тесты для ContentInfoGetter"""

    @pytest.fixture
    def mock_dependencies(self):
        """Создает моки всех зависимостей"""
        config = Mock(spec=IConfig)
        http_factory = Mock(spec=IHttpClientFactory)
        proxy_generator = Mock(spec=IProxyGenerator)
        timeout_configurator = Mock(spec=ITimeoutConfigurator)

        return {
            'config': config,
            'http_factory': http_factory,
            'proxy_generator': proxy_generator,
            'timeout_configurator': timeout_configurator
        }

    @pytest.fixture
    def content_info_getter(self, mock_dependencies):
        """Создает экземпляр ContentInfoGetter с моками зависимостей"""
        return ContentInfoGetter(**mock_dependencies)

    @pytest.mark.asyncio
    async def test_get_content_info_successful_head(self, content_info_getter, mock_dependencies):
        """Тест успешного HEAD запроса"""
        # Arrange
        url = "https://example.com/video.mp4"
        headers = {"User-Agent": "test-agent"}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        # Правильное мокирование асинхронного контекстного менеджера
        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "video/mp4", "content-length": "1024"}
        mock_client.head.return_value = mock_response

        # Настраиваем асинхронный контекстный менеджер
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client
        mock_dependencies['http_factory'].create_client.return_value.__aexit__.return_value = None

        # Act
        result = await content_info_getter.get_content_info(url, headers, use_head=True)

        # Assert
        assert result.status_code == 200
        assert result.content_type == "video/mp4"
        assert result.content_length == 1024
        assert result.method_used == "HEAD"
        mock_dependencies['http_factory'].create_client.assert_called_once()
        mock_client.head.assert_called_once_with(url)

    @pytest.mark.asyncio
    async def test_get_content_info_head_zero_length_falls_back_to_get(self, content_info_getter, mock_dependencies):
        """Тест когда HEAD возвращает content_length=0 и переключается на GET"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        # HEAD запрос возвращает 0 content_length
        mock_client_head = AsyncMock()
        mock_response_head = Mock()
        mock_response_head.status_code = 200
        mock_response_head.headers = {"content-type": "video/mp4", "content-length": "0"}
        mock_client_head.head.return_value = mock_response_head

        # GET запрос успешен
        mock_client_get = AsyncMock()
        mock_response_stream = AsyncMock()
        mock_response_stream.status_code = 206
        mock_response_stream.headers = {"content-range": "bytes 0-0/2048", "content-type": "video/mp4"}
        mock_client_get.stream.return_value.__aenter__.return_value = mock_response_stream

        # Чередуем возвращаемые клиенты
        mock_dependencies['http_factory'].create_client.side_effect = [
            AsyncMock().__aenter__.return_value.__aenter__.return_value if i == 0 else
            AsyncMock().__aenter__.return_value.__aenter__.return_value
            for i in range(2)
        ]
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.side_effect = [mock_client_head, mock_client_get]

        # Act
        result = await content_info_getter.get_content_info(url, use_head=True)

        # Assert
        assert result.content_length == 2048
        assert result.method_used == "GET_Range 0-0"

    @pytest.mark.asyncio
    async def test_get_content_info_head_exception_falls_back_to_get(self, content_info_getter, mock_dependencies):
        """Тест когда HEAD выбрасывает исключение и переключается на GET"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        # HEAD запрос выбрасывает исключение
        mock_client_head = AsyncMock()
        mock_client_head.head.side_effect = httpx.RequestError("Connection error")

        # GET запрос успешен
        mock_client_get = AsyncMock()
        mock_response_stream = AsyncMock()
        mock_response_stream.status_code = 200
        mock_response_stream.headers = {"content-type": "video/mp4", "content-length": "1024"}
        mock_client_get.stream.return_value.__aenter__.return_value = mock_response_stream

        mock_dependencies['http_factory'].create_client.side_effect = [
            AsyncMock().__aenter__.return_value for _ in range(2)
        ]
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.side_effect = [mock_client_head, mock_client_get]

        # Act
        result = await content_info_getter.get_content_info(url, use_head=True)

        # Assert
        assert result.content_length == 1024
        assert "GET" in result.method_used
        assert result.error is None

    @pytest.mark.asyncio
    async def test_get_content_info_use_head_false_direct_get(self, content_info_getter, mock_dependencies):
        """Тест когда use_head=False и сразу используется GET"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response_stream = AsyncMock()
        mock_response_stream.status_code = 200
        mock_response_stream.headers = {"content-type": "video/mp4", "content-length": "1024"}
        mock_client.stream.return_value.__aenter__.return_value = mock_response_stream

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await content_info_getter.get_content_info(url, use_head=False)

        # Assert
        assert result.content_length == 1024
        assert "GET" in result.method_used
        mock_client.head.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_content_info_all_methods_fail(self, content_info_getter, mock_dependencies, caplog):
        """Тест когда все методы (HEAD и все GET стратегии) завершаются ошибкой"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        # Все запросы выбрасывают исключения
        mock_client = AsyncMock()
        mock_client.head.side_effect = Exception("HEAD failed")
        mock_client.stream.side_effect = Exception("GET failed")

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        with caplog.at_level('WARNING'):
            result = await content_info_getter.get_content_info(url, use_head=True)

        # Assert
        assert result.status_code == 0
        assert result.content_length == 0
        assert result.method_used == "GET_ALL_FAILED"
        assert "All GET strategies failed" in result.error

    @pytest.mark.asyncio
    async def test_get_content_info_with_proxy(self, content_info_getter, mock_dependencies):
        """Тест использования прокси"""
        # Arrange
        url = "https://example.com/video.mp4"
        proxy_url = "http://proxy.example.com:8080"

        mock_dependencies['proxy_generator'].has_proxies.return_value = True
        mock_dependencies['proxy_generator'].get_proxy.return_value = proxy_url
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "video/mp4", "content-length": "1024"}
        mock_client.head.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await content_info_getter.get_content_info(url, use_head=True)

        # Assert
        mock_dependencies['proxy_generator'].get_proxy.assert_called()
        mock_dependencies['proxy_generator'].mark_success.assert_called_with(proxy_url)

    @pytest.mark.asyncio
    async def test_get_content_info_head_with_proxy_failure(self, content_info_getter, mock_dependencies):
        """Тест когда HEAD с прокси завершается ошибкой"""
        # Arrange
        url = "https://example.com/video.mp4"
        proxy_url = "http://proxy.example.com:8080"

        mock_dependencies['proxy_generator'].has_proxies.return_value = True
        mock_dependencies['proxy_generator'].get_proxy.return_value = proxy_url
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_client.head.side_effect = httpx.RequestError("Proxy connection failed")
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await content_info_getter._try_head_request(url, {})

        # Assert
        assert result.status_code == 0
        assert "Proxy connection failed" in result.error
        assert result.method_used == "HEAD"
        mock_dependencies['proxy_generator'].mark_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_try_head_request_success(self, content_info_getter, mock_dependencies):
        """Тест успешного HEAD запроса через отдельный метод"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "video/mp4", "content-length": "1024", "accept-ranges": "bytes"}
        mock_client.head.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await content_info_getter._try_head_request(url, {})

        # Assert
        assert result.status_code == 200
        assert result.content_type == "video/mp4"
        assert result.content_length == 1024
        assert result.accept_ranges == "bytes"
        assert result.method_used == "HEAD"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_try_head_request_invalid_content_length(self, content_info_getter, mock_dependencies):
        """Тест HEAD запроса с некорректным content-length"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "video/mp4", "content-length": "invalid"}
        mock_client.head.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await content_info_getter._try_head_request(url, {})

        # Assert
        assert result.status_code == 200
        assert result.content_length == 0

    @pytest.mark.asyncio
    async def test_try_get_requests_success_first_strategy(self, content_info_getter, mock_dependencies):
        """Тест успешного GET запроса с первой стратегией"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response_stream = AsyncMock()
        mock_response_stream.status_code = 206
        mock_response_stream.headers = {
            "content-range": "bytes 0-0/2048",
            "content-type": "video/mp4",
            "accept-ranges": "bytes"
        }
        mock_client.stream.return_value.__aenter__.return_value = mock_response_stream
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await content_info_getter._try_get_requests(url, {})

        # Assert
        assert result.status_code == 206
        assert result.content_length == 2048
        assert result.method_used == "GET_Range 0-0"

    @pytest.mark.asyncio
    async def test_try_get_requests_success_second_strategy(self, content_info_getter, mock_dependencies):
        """Тест успешного GET запроса со второй стратегией"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()

        # Первая стратегия падает, вторая успешна
        mock_response_stream_fail = AsyncMock()
        mock_response_stream_fail.__aenter__.side_effect = httpx.RequestError("First strategy failed")

        mock_response_stream_success = AsyncMock()
        mock_response_stream_success.status_code = 206
        mock_response_stream_success.headers = {
            "content-range": "bytes 0-999/4096",
            "content-type": "video/mp4",
            "accept-ranges": "bytes"
        }

        mock_client.stream.side_effect = [
            mock_response_stream_fail,
            mock_response_stream_success
        ]

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await content_info_getter._try_get_requests(url, {})

        # Assert
        assert result.status_code == 206
        assert result.content_length == 4096
        assert result.method_used == "GET_Range 0-999"

    @pytest.mark.asyncio
    async def test_try_get_requests_success_third_strategy_content_length(self, content_info_getter, mock_dependencies):
        """Тест успешного GET запроса с третьей стратегией"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()

        # Первые две стратегии падают, третья успешна
        mock_response_stream_fail = AsyncMock()
        mock_response_stream_fail.__aenter__.side_effect = httpx.RequestError("Strategy failed")

        mock_response_stream_success = AsyncMock()
        mock_response_stream_success.status_code = 200
        mock_response_stream_success.headers = {
            "content-type": "video/mp4",
            "content-length": "8192",
            "accept-ranges": "bytes"
        }

        mock_client.stream.side_effect = [
            mock_response_stream_fail,
            mock_response_stream_fail,
            mock_response_stream_success
        ]

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await content_info_getter._try_get_requests(url, {})

        # Assert
        assert result.status_code == 200
        assert result.content_length == 8192
        assert result.method_used == "GET_SIMPLE"

    @pytest.mark.asyncio
    async def test_try_get_requests_invalid_content_length(self, content_info_getter, mock_dependencies):
        """Тест GET запроса с некорректным content-length"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response_stream = AsyncMock()
        mock_response_stream.status_code = 200
        mock_response_stream.headers = {
            "content-type": "video/mp4",
            "content-length": "invalid",
            "accept-ranges": "bytes"
        }
        mock_client.stream.return_value.__aenter__.return_value = mock_response_stream
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await content_info_getter._try_get_requests(url, {})

        # Assert
        assert result.status_code == 200
        assert result.content_length == 0

    @pytest.mark.asyncio
    async def test_try_get_requests_with_proxy_failure(self, content_info_getter, mock_dependencies):
        """Тест GET запросов с прокси"""
        # Arrange
        url = "https://example.com/video.mp4"
        proxy_url = "http://proxy.example.com:8080"

        mock_dependencies['proxy_generator'].has_proxies.return_value = True
        mock_dependencies['proxy_generator'].get_proxy.return_value = proxy_url
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response_stream = AsyncMock()
        mock_response_stream.__aenter__.side_effect = httpx.RequestError("Proxy GET failed")
        mock_client.stream.return_value = mock_response_stream
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        result = await content_info_getter._try_get_requests(url, {})

        # Assert
        assert result.method_used == "GET_ALL_FAILED"
        assert mock_dependencies['proxy_generator'].mark_failure.call_count == 3

    @pytest.mark.asyncio
    async def test_try_get_requests_content_range_parsing(self, content_info_getter, mock_dependencies):
        """Тест парсинга content-range"""
        test_cases = [
            ("bytes 0-999/5000", 5000),
            ("bytes */1000", 1000),
            ("bytes 50-100/2000", 2000),
        ]

        for content_range, expected_length in test_cases:
            mock_dependencies['proxy_generator'].has_proxies.return_value = False
            mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

            mock_client = AsyncMock()
            mock_response_stream = AsyncMock()
            mock_response_stream.status_code = 206
            mock_response_stream.headers = {
                "content-range": content_range,
                "content-type": "video/mp4",
                "accept-ranges": "bytes"
            }
            mock_client.stream.return_value.__aenter__.return_value = mock_response_stream
            mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

            result = await content_info_getter._try_get_requests("https://example.com/video.mp4", {})

            assert result.content_length == expected_length

    @pytest.mark.asyncio
    async def test_get_content_info_exception_handling(self, content_info_getter, mock_dependencies):
        """Тест обработки исключений"""
        # Arrange
        url = "https://example.com/video.mp4"

        mock_dependencies['timeout_configurator'].create_timeout_config.side_effect = Exception("Config error")

        # Act
        result = await content_info_getter.get_content_info(url)

        # Assert
        assert result.status_code == 0
        assert result.method_used == "ERROR"
        assert "Config error" in result.error

    def test_initialization(self, mock_dependencies):
        """Тест инициализации"""
        getter = ContentInfoGetter(**mock_dependencies)

        assert getter.config == mock_dependencies['config']
        assert getter.http_factory == mock_dependencies['http_factory']
        assert getter.proxy_generator == mock_dependencies['proxy_generator']
        assert getter.timeout_configurator == mock_dependencies['timeout_configurator']
        assert getter.logger.name == 'lampa-proxy-content-getter'

    @pytest.mark.asyncio
    async def test_default_headers(self, content_info_getter, mock_dependencies):
        """Тест headers по умолчанию"""
        url = "https://example.com/video.mp4"

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "video/mp4", "content-length": "1024"}
        mock_client.head.return_value = mock_response

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        result = await content_info_getter.get_content_info(url)

        assert result.status_code == 200
        mock_dependencies['http_factory'].create_client.assert_called_once()