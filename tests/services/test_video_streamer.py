import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, call
from typing import Dict, Optional
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from src.models.interfaces import IConfig, IHttpClientFactory, IContentInfoGetter, IProxyGenerator, ITimeoutConfigurator
from src.models.responses import ContentInfoResponse
from src.services.video_streamer import VideoStreamer


class TestVideoStreamer:
    """Тесты для VideoStreamer"""

    @pytest.fixture
    def mock_dependencies(self):
        """Создает моки всех зависимостей"""
        config = Mock(spec=IConfig)
        http_factory = Mock(spec=IHttpClientFactory)
        content_getter = Mock(spec=IContentInfoGetter)
        proxy_generator = Mock(spec=IProxyGenerator)
        timeout_configurator = Mock(spec=ITimeoutConfigurator)

        # Настройка конфигурации по умолчанию
        config.stream_chunk_size = 8192
        config.max_range_size = 10485760  # 10MB

        return {
            'config': config,
            'http_factory': http_factory,
            'content_getter': content_getter,
            'proxy_generator': proxy_generator,
            'timeout_configurator': timeout_configurator
        }

    @pytest.fixture
    def video_streamer(self, mock_dependencies):
        """Создает экземпляр VideoStreamer с моками зависимостей"""
        return VideoStreamer(**mock_dependencies)

    def test_initialization(self, mock_dependencies):
        """Тест инициализации VideoStreamer"""
        # Act
        streamer = VideoStreamer(**mock_dependencies)

        # Assert
        assert streamer.config == mock_dependencies['config']
        assert streamer.http_factory == mock_dependencies['http_factory']
        assert streamer.content_getter == mock_dependencies['content_getter']
        assert streamer.proxy_generator == mock_dependencies['proxy_generator']
        assert streamer.timeout_configurator == mock_dependencies['timeout_configurator']
        assert streamer.logger.name == 'lampa-proxy-video-streamer'

    @pytest.mark.asyncio
    async def test_stream_video_success_without_range(self, video_streamer, mock_dependencies, caplog):
        """Тест успешной потоковой передачи без range заголовка"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {"User-Agent": "test"}

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="video/mp4",
            content_length=1024000,  # 1MB
            accept_ranges="bytes",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        # Мокируем создание генератора потока
        video_streamer._create_stream_generator = AsyncMock(return_value=AsyncMock())

        # Act
        with caplog.at_level('INFO'):
            result = await video_streamer.stream_video(target_url, request_headers)

        # Assert
        assert isinstance(result, StreamingResponse)
        assert result.media_type == "video/mp4"
        assert result.status_code == 200
        assert 'Content-Length' in result.headers
        assert result.headers['Content-Length'] == '1024000'
        assert 'Content-Range' not in result.headers

        mock_dependencies['content_getter'].get_content_info.assert_called_once_with(
            target_url, request_headers, use_head=True
        )
        assert "Streaming video with range support from:" in caplog.text
        assert "Content info: status=200, size=1024000, type=video/mp4" in caplog.text

    @pytest.mark.asyncio
    async def test_stream_video_success_with_range(self, video_streamer, mock_dependencies, caplog):
        """Тест успешной потоковой передачи с range заголовком"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {"User-Agent": "test"}
        range_header = "bytes=0-999"

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="video/mp4",
            content_length=1024000,
            accept_ranges="bytes",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        video_streamer._create_stream_generator = AsyncMock(return_value=AsyncMock())

        # Act
        with caplog.at_level('INFO'):
            result = await video_streamer.stream_video(target_url, request_headers, range_header)

        # Assert
        assert isinstance(result, StreamingResponse)
        assert result.status_code == 206  # Partial Content
        assert 'Content-Range' in result.headers
        assert 'Content-Length' in result.headers
        assert result.headers['Content-Length'] == '1000'  # 1000 bytes (0-999)

        assert "Requested range: 0-999 (file size: 1024000)" in caplog.text
        assert "Sending Range to source: bytes=0-999" in caplog.text

    @pytest.mark.asyncio
    async def test_stream_video_content_info_error(self, video_streamer, mock_dependencies):
        """Тест когда получение информации о контенте завершается ошибкой"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {}

        content_info = ContentInfoResponse(
            status_code=0,
            content_type="",
            content_length=0,
            accept_ranges="",
            headers={},
            method_used="HEAD",
            error="Connection failed"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await video_streamer.stream_video(target_url, request_headers)

        assert exc_info.value.status_code == 500
        assert "Failed to get video info: Connection failed" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_stream_video_unknown_file_size(self, video_streamer, mock_dependencies, caplog):
        """Тест потоковой передачи с неизвестным размером файла"""
        # Arrange
        target_url = "https://example.com/live-stream"
        request_headers = {}

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="video/mp4",
            content_length=0,  # Неизвестный размер
            accept_ranges="bytes",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        video_streamer._create_stream_generator = AsyncMock(return_value=AsyncMock())

        # Act
        with caplog.at_level('WARNING'):
            result = await video_streamer.stream_video(target_url, request_headers)

        # Assert
        assert isinstance(result, StreamingResponse)
        assert result.status_code == 200
        assert 'Content-Length' not in result.headers
        assert "File size is unknown, range requests may not work properly" in caplog.text

    @pytest.mark.asyncio
    async def test_create_stream_generator_success(self, video_streamer, mock_dependencies, caplog):
        """Тест успешного создания генератора потока"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {"Range": "bytes=0-999"}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 206
        mock_response.headers = {
            'content-type': 'video/mp4',
            'content-range': 'bytes 0-999/1024000',
            'content-length': '1000'
        }

        # Симулируем поток данных
        chunks = [b'chunk1', b'chunk2', b'chunk3']
        mock_response.aiter_bytes.return_value = AsyncMock()
        mock_response.aiter_bytes.return_value.__aiter__.return_value = iter(chunks)

        mock_client.stream.return_value.__aenter__.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        generator = video_streamer._create_stream_generator(target_url, request_headers)

        # Проверяем генератор
        received_chunks = []
        async for chunk in generator:
            received_chunks.append(chunk)

        # Assert
        assert received_chunks == chunks
        mock_dependencies['http_factory'].create_client.assert_called_with(
            headers=request_headers,
            is_video=True,
            follow_redirects=True,
            verify_ssl=False,
            proxy=None,
            timeout=Mock()
        )
        mock_client.stream.assert_called_with('GET', target_url)
        assert "Source response status: 206" in caplog.text

    @pytest.mark.asyncio
    async def test_create_stream_generator_with_proxy(self, video_streamer, mock_dependencies):
        """Тест создания генератора потока с прокси"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {}
        proxy_url = "http://proxy.example.com:8080"

        mock_dependencies['proxy_generator'].has_proxies.return_value = True
        mock_dependencies['proxy_generator'].get_proxy.return_value = proxy_url
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.aiter_bytes.return_value = AsyncMock()
        mock_response.aiter_bytes.return_value.__aiter__.return_value = iter([b'data'])

        mock_client.stream.return_value.__aenter__.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        async for _ in video_streamer._create_stream_generator(target_url, request_headers):
            pass

        # Assert
        mock_dependencies['proxy_generator'].mark_success.assert_called_with(proxy_url)
        mock_dependencies['timeout_configurator'].create_timeout_config.assert_called_with(30.0)
        mock_dependencies['http_factory'].create_client.assert_called_with(
            headers=request_headers,
            is_video=True,
            follow_redirects=True,
            verify_ssl=False,
            proxy=proxy_url,
            timeout=Mock()
        )

    @pytest.mark.asyncio
    async def test_create_stream_generator_404_error(self, video_streamer, mock_dependencies, caplog):
        """Тест обработки 404 ошибки"""
        # Arrange
        target_url = "https://example.com/missing-video.mp4"
        request_headers = {}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.headers = {}

        mock_client.stream.return_value.__aenter__.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        generator = video_streamer._create_stream_generator(target_url, request_headers)

        # Должен завершиться без данных
        chunks = []
        async for chunk in generator:
            chunks.append(chunk)

        # Assert
        assert chunks == []
        assert "Video not found (404):" in caplog.text

    @pytest.mark.asyncio
    async def test_create_stream_generator_416_error(self, video_streamer, mock_dependencies, caplog):
        """Тест обработки 416 ошибки (Range Not Satisfiable)"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 416
        mock_response.headers = {}

        mock_client.stream.return_value.__aenter__.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        generator = video_streamer._create_stream_generator(target_url, request_headers)

        chunks = []
        async for chunk in generator:
            chunks.append(chunk)

        # Assert
        assert chunks == []
        assert "Range not satisfiable (416):" in caplog.text

    @pytest.mark.asyncio
    async def test_create_stream_generator_server_error(self, video_streamer, mock_dependencies, caplog):
        """Тест обработки ошибки сервера (5xx)"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.headers = {}

        mock_client.stream.return_value.__aenter__.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        generator = video_streamer._create_stream_generator(target_url, request_headers)

        chunks = []
        async for chunk in generator:
            chunks.append(chunk)

        # Assert
        assert chunks == []
        assert "Source server error 500:" in caplog.text

    @pytest.mark.asyncio
    async def test_create_stream_generator_cancelled_error(self, video_streamer, mock_dependencies, caplog):
        """Тест обработки CancelledError"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        # Симулируем CancelledError при итерации
        async def chunks_with_cancel():
            yield b'chunk1'
            raise asyncio.CancelledError()

        mock_response.aiter_bytes.return_value = chunks_with_cancel()

        mock_client.stream.return_value.__aenter__.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        generator = video_streamer._create_stream_generator(target_url, request_headers)

        chunks = []
        try:
            async for chunk in generator:
                chunks.append(chunk)
        except asyncio.CancelledError:
            pass

        # Assert
        assert chunks == [b'chunk1']
        assert "Video stream was cancelled by client" in caplog.text

    @pytest.mark.asyncio
    async def test_create_stream_generator_exception(self, video_streamer, mock_dependencies, caplog):
        """Тест обработки общего исключения"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {}
        proxy_url = "http://proxy.example.com:8080"

        mock_dependencies['proxy_generator'].has_proxies.return_value = True
        mock_dependencies['proxy_generator'].get_proxy.return_value = proxy_url
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_client.stream.side_effect = Exception("Streaming error")

        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        generator = video_streamer._create_stream_generator(target_url, request_headers)

        chunks = []
        async for chunk in generator:
            chunks.append(chunk)

        # Assert
        assert chunks == []
        mock_dependencies['proxy_generator'].mark_failure.assert_called_with(proxy_url)
        assert "Video stream error: Streaming error" in caplog.text

    @pytest.mark.asyncio
    async def test_create_stream_generator_stop_iteration(self, video_streamer, mock_dependencies, caplog):
        """Тест остановки генератора при достижении ожидаемого количества байт"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 206
        mock_response.headers = {
            'content-range': 'bytes 0-999/1024000',  # Ожидается 1000 байт
            'content-length': '1000'
        }

        # Первый чанк уже достигает ожидаемого количества
        chunks = [b'x' * 1000, b'should_not_be_yielded']
        mock_response.aiter_bytes.return_value = AsyncMock()
        mock_response.aiter_bytes.return_value.__aiter__.return_value = iter(chunks)

        mock_client.stream.return_value.__aenter__.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        generator = video_streamer._create_stream_generator(target_url, request_headers)

        received_chunks = []
        async for chunk in generator:
            received_chunks.append(chunk)

        # Assert
        assert len(received_chunks) == 1  # Только первый чанк
        assert received_chunks[0] == b'x' * 1000
        assert "Reached expected end of stream: 1000/1000 bytes" in caplog.text

    def test_get_expected_bytes_from_content_range(self, video_streamer, caplog):
        """Тест получения ожидаемого количества байт из content-range"""
        # Arrange
        content_range = "bytes 100-199/1000"
        content_length = "100"

        # Act
        with caplog.at_level('INFO'):
            result = video_streamer._get_expected_bytes(content_range, content_length)

        # Assert
        assert result == 100  # 199-100+1 = 100
        assert "Expected bytes from Content-Range: 100" in caplog.text

    def test_get_expected_bytes_from_content_length(self, video_streamer, caplog):
        """Тест получения ожидаемого количества байт из content-length"""
        # Arrange
        content_range = ""
        content_length = "500"

        # Act
        with caplog.at_level('INFO'):
            result = video_streamer._get_expected_bytes(content_range, content_length)

        # Assert
        assert result == 500
        assert "Expected bytes from Content-Length: 500" in caplog.text

    def test_get_expected_bytes_invalid_content_length(self, video_streamer):
        """Тест обработки невалидного content-length"""
        # Arrange
        content_range = ""
        content_length = "invalid"

        # Act
        result = video_streamer._get_expected_bytes(content_range, content_length)

        # Assert
        assert result == 0

    def test_get_expected_bytes_no_info(self, video_streamer):
        """Тест когда нет информации о количестве байт"""
        # Arrange
        content_range = ""
        content_length = "unknown"

        # Act
        result = video_streamer._get_expected_bytes(content_range, content_length)

        # Assert
        assert result == 0

    def test_get_expected_bytes_invalid_content_range_format(self, video_streamer):
        """Тест обработки невалидного формата content-range"""
        # Arrange
        content_range = "invalid-format"
        content_length = "100"

        # Act
        result = video_streamer._get_expected_bytes(content_range, content_length)

        # Assert
        assert result == 0

    def test_prepare_response_headers_with_range(self, video_streamer, caplog):
        """Тест подготовки заголовков ответа с range"""
        # Arrange
        content_type = "video/mp4"
        range_requested = True
        start_byte = 100
        end_byte = 199
        file_size = 1000

        # Act
        with caplog.at_level('INFO'):
            headers = video_streamer._prepare_response_headers(
                content_type, range_requested, start_byte, end_byte, file_size
            )

        # Assert
        assert headers['Content-Type'] == 'video/mp4'
        assert headers['Accept-Ranges'] == 'bytes'
        assert headers['Content-Range'] == 'bytes 100-199/1000'
        assert headers['Content-Length'] == '100'  # 199-100+1 = 100
        assert "Sending 206 Partial Content: 100 bytes (range: 100-199)" in caplog.text

    def test_prepare_response_headers_without_range_known_size(self, video_streamer, caplog):
        """Тест подготовки заголовков ответа без range с известным размером"""
        # Arrange
        content_type = "video/mp4"
        range_requested = False
        start_byte = 0
        end_byte = 999
        file_size = 1000

        # Act
        with caplog.at_level('INFO'):
            headers = video_streamer._prepare_response_headers(
                content_type, range_requested, start_byte, end_byte, file_size
            )

        # Assert
        assert 'Content-Range' not in headers
        assert headers['Content-Length'] == '1000'
        assert "Sending 200 OK: 1000 bytes" in caplog.text

    def test_prepare_response_headers_unknown_size(self, video_streamer, caplog):
        """Тест подготовки заголовков ответа с неизвестным размером"""
        # Arrange
        content_type = "video/mp4"
        range_requested = False
        start_byte = 0
        end_byte = 0
        file_size = 0  # Неизвестный размер

        # Act
        with caplog.at_level('INFO'):
            headers = video_streamer._prepare_response_headers(
                content_type, range_requested, start_byte, end_byte, file_size
            )

        # Assert
        assert 'Content-Length' not in headers
        assert 'Content-Range' not in headers
        assert "Sending response without Content-Length (unknown file size)" in caplog.text

    def test_parse_range_header_no_header(self, video_streamer):
        """Тест парсинга без range заголовка"""
        # Arrange
        range_header = None
        file_size = 1000

        # Act
        start, end = video_streamer._parse_range_header(range_header, file_size)

        # Assert
        assert start == 0
        assert end == 999

    def test_parse_range_header_valid_range(self, video_streamer, caplog):
        """Тест парсинга валидного range заголовка"""
        # Arrange
        range_header = "bytes=100-199"
        file_size = 1000

        # Act
        with caplog.at_level('DEBUG'):
            start, end = video_streamer._parse_range_header(range_header, file_size)

        # Assert
        assert start == 100
        assert end == 199
        assert "Parsed range: 100-199 (file size: 1000)" in caplog.text

    def test_parse_range_header_open_ended_range(self, video_streamer):
        """Тест парсинга range заголовка без конечной позиции"""
        # Arrange
        range_header = "bytes=500-"
        file_size = 1000

        # Act
        start, end = video_streamer._parse_range_header(range_header, file_size)

        # Assert
        assert start == 500
        assert end == 999

    def test_parse_range_header_open_ended_range_unknown_size(self, video_streamer):
        """Тест парсинга range заголовка без конечной позиции и неизвестного размера"""
        # Arrange
        range_header = "bytes=500-"
        file_size = 0

        # Act
        start, end = video_streamer._parse_range_header(range_header, file_size)

        # Assert
        assert start == 500
        assert end == 0

    def test_parse_range_header_invalid_format(self, video_streamer, caplog):
        """Тест парсинга невалидного формата range заголовка"""
        # Arrange
        range_header = "invalid-format"
        file_size = 1000

        # Act
        with caplog.at_level('ERROR'):
            start, end = video_streamer._parse_range_header(range_header, file_size)

        # Assert
        assert start == 0
        assert end == 999
        assert "Error parsing range header 'invalid-format'" in caplog.text

    def test_parse_range_header_start_after_file_size(self, video_streamer):
        """Тест когда начальная позиция больше размера файла"""
        # Arrange
        range_header = "bytes=2000-2999"
        file_size = 1000

        # Act
        start, end = video_streamer._parse_range_header(range_header, file_size)

        # Assert
        assert start == 999
        assert end == 999

    def test_parse_range_header_end_after_file_size(self, video_streamer):
        """Тест когда конечная позиция больше размера файла"""
        # Arrange
        range_header = "bytes=500-1500"
        file_size = 1000

        # Act
        start, end = video_streamer._parse_range_header(range_header, file_size)

        # Assert
        assert start == 500
        assert end == 999

    def test_parse_range_header_exceeds_max_range_size(self, video_streamer, mock_dependencies):
        """Тест когда диапазон превышает максимальный размер"""
        # Arrange
        range_header = "bytes=0-20000000"  # 20MB
        file_size = 50000000  # 50MB
        mock_dependencies['config'].max_range_size = 10485760  # 10MB

        # Act
        start, end = video_streamer._parse_range_header(range_header, file_size)

        # Assert
        assert start == 0
        assert end == 10485759  # 0 + 10MB - 1

    def test_parse_range_header_negative_start(self, video_streamer):
        """Тест с отрицательной начальной позицией"""
        # Arrange
        range_header = "bytes=-100-200"
        file_size = 1000

        # Act
        start, end = video_streamer._parse_range_header(range_header, file_size)

        # Assert
        # Должен вернуться диапазон по умолчанию из-за ошибки парсинга
        assert start == 0
        assert end == 999

    def test_parse_range_header_start_greater_than_end(self, video_streamer):
        """Тест когда начальная позиция больше конечной"""
        # Arrange
        range_header = "bytes=200-100"
        file_size = 1000

        # Act
        start, end = video_streamer._parse_range_header(range_header, file_size)

        # Assert
        # Должны быть поменяны местами
        assert start == 100
        assert end == 200

    @pytest.mark.asyncio
    async def test_stream_video_range_header_processing(self, video_streamer, mock_dependencies):
        """Тест обработки различных вариантов range заголовка"""
        # Arrange
        target_url = "https://example.com/video.mp4"

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="video/mp4",
            content_length=1000,
            accept_ranges="bytes",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info
        video_streamer._create_stream_generator = AsyncMock(return_value=AsyncMock())

        test_cases = [
            (None, False),  # Без range
            ("bytes=0-499", True),  # С range
            ("bytes=500-", True),  # Открытый range
        ]

        for range_header, should_have_range in test_cases:
            # Act
            result = await video_streamer.stream_video(target_url, {}, range_header)

            # Assert
            if should_have_range:
                assert result.status_code == 206
                assert 'Content-Range' in result.headers
            else:
                assert result.status_code == 200
                assert 'Content-Range' not in result.headers

    @pytest.mark.asyncio
    async def test_create_stream_generator_logging(self, video_streamer, mock_dependencies, caplog):
        """Тест логирования в генераторе потока"""
        # Arrange
        target_url = "https://example.com/video.mp4"
        request_headers = {}

        mock_dependencies['proxy_generator'].has_proxies.return_value = False
        mock_dependencies['timeout_configurator'].create_timeout_config.return_value = Mock()

        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {
            'content-type': 'video/mp4',
            'content-length': '1000'
        }
        mock_response.aiter_bytes.return_value = AsyncMock()
        mock_response.aiter_bytes.return_value.__aiter__.return_value = iter([b'chunk1', b'chunk2'])

        mock_client.stream.return_value.__aenter__.return_value = mock_response
        mock_dependencies['http_factory'].create_client.return_value.__aenter__.return_value = mock_client

        # Act
        with caplog.at_level('INFO'):
            async for _ in video_streamer._create_stream_generator(target_url, request_headers):
                pass

        # Assert
        assert "Video content-type: video/mp4" in caplog.text
        assert "Content-Length: 1000" in caplog.text
        assert "Video stream completed: 12 bytes streamed" in caplog.text  # 6 + 6 bytes