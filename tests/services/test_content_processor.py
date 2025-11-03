import pytest
import urllib.parse
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from src.models.interfaces import IConfig, IHttpClientFactory, IContentInfoGetter, IVideoStreamer, IRequestProcessor
from src.models.responses import ContentInfoResponse
from src.services.content_processor import ContentProcessor


class TestContentProcessor:
    """Тесты для ContentProcessor"""

    @pytest.fixture
    def mock_dependencies(self):
        """Создает моки всех зависимостей"""
        config = Mock(spec=IConfig)
        http_factory = Mock(spec=IHttpClientFactory)
        content_getter = Mock(spec=IContentInfoGetter)
        video_streamer = Mock(spec=IVideoStreamer)
        request_processor = Mock(spec=IRequestProcessor)

        config.video_extensions = ['.mp4', '.avi', '.mkv', '.mov']
        config.video_patterns = ['/video/', '/stream/', 'video=true']
        config.video_indicators = ['video/mp4', 'video/avi', 'video/x-matroska', 'video/quicktime', 'application/video+mp4']

        return {
            'config': config,
            'http_factory': http_factory,
            'content_getter': content_getter,
            'video_streamer': video_streamer,
            'request_processor': request_processor
        }

    @pytest.fixture
    def content_processor(self, mock_dependencies):
        """Создает экземпляр ContentProcessor с моками зависимостей"""
        return ContentProcessor(**mock_dependencies)

    @pytest.mark.asyncio
    async def test_process_content_get_video(self, content_processor, mock_dependencies):
        """Тест обработки GET запроса для видео контента"""
        url = "https://example.com/video.mp4"
        headers = {"User-Agent": "test"}
        range_header = "bytes=0-1000"

        content_processor._is_video_content = AsyncMock(return_value=True)

        expected_result = Mock()
        mock_dependencies['video_streamer'].stream_video.return_value = expected_result

        result = await content_processor.process_content(url, 'GET', None, headers, range_header)

        content_processor._is_video_content.assert_called_once_with(url, headers)
        mock_dependencies['video_streamer'].stream_video.assert_called_once_with(url, headers, range_header)
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_process_content_get_non_video(self, content_processor, mock_dependencies):
        """Тест обработки GET запроса для не-видео контента"""
        url = "https://example.com/image.jpg"
        headers = {"User-Agent": "test"}

        content_processor._is_video_content = AsyncMock(return_value=False)

        expected_result = Mock()
        async def mock_process_request(*args, **kwargs):
            yield expected_result

        mock_dependencies['request_processor'].process_request = mock_process_request

        result = await content_processor.process_content(url, 'GET', None, headers)

        content_processor._is_video_content.assert_called_once_with(url, headers)
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_process_content_non_get_method(self, content_processor, mock_dependencies):
        """Тест обработки не-GET запросов"""
        url = "https://example.com/api/upload"
        method = "POST"
        data = {"key": "value"}
        headers = {"Content-Type": "application/json"}

        expected_result = Mock()
        async def mock_process_request(*args, **kwargs):
            yield expected_result

        mock_dependencies['request_processor'].process_request = mock_process_request

        result = await content_processor.process_content(url, method, data, headers)

        content_processor._is_video_content.assert_not_called()
        mock_dependencies['video_streamer'].stream_video.assert_not_called()
        assert result == expected_result

    @pytest.mark.asyncio
    async def test_process_content_default_headers(self, content_processor, mock_dependencies):
        """Тест обработки с headers по умолчанию"""
        url = "https://example.com/test"

        expected_result = Mock()
        async def mock_process_request(*args, **kwargs):
            yield expected_result

        mock_dependencies['request_processor'].process_request = mock_process_request

        result = await content_processor.process_content(url, 'GET')

        assert result == expected_result

    @pytest.mark.asyncio
    async def test_is_video_content_success_by_content_type(self, content_processor, mock_dependencies):
        """Тест проверки видео контента по content-type"""
        url = "https://example.com/video.mp4"
        headers = {"Accept": "*/*"}

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="video/mp4",
            content_length=1024000,
            accept_ranges="bytes",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        result = await content_processor._is_video_content(url, headers)

        assert result is True
        mock_dependencies['content_getter'].get_content_info.assert_called_once_with(url, headers, use_head=True)

    @pytest.mark.asyncio
    async def test_is_video_content_success_by_octet_stream_with_video_url(self, content_processor, mock_dependencies):
        """Тест проверки видео контента для octet-stream с видео URL"""
        url = "https://example.com/video.mp4"
        headers = {"Accept": "*/*"}

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="application/octet-stream",
            content_length=1024000,
            accept_ranges="bytes",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        result = await content_processor._is_video_content(url, headers)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_video_content_success_by_size_and_range(self, content_processor, mock_dependencies, caplog):
        """Тест проверки видео контента по размеру и поддержке range"""
        url = "https://example.com/largefile.bin"
        headers = {"Accept": "*/*"}

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="application/octet-stream",
            content_length=2000000,
            accept_ranges="bytes",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        with patch.object(content_processor, '_is_video_url', return_value=True):
            with caplog.at_level('INFO'):
                result = await content_processor._is_video_content(url, headers)

            assert result is True
            assert "Possible video detected by size and range support: 2000000 bytes" in caplog.text

    @pytest.mark.asyncio
    async def test_is_video_content_non_200_status(self, content_processor, mock_dependencies):
        """Тест проверки видео контента с статусом не 200/206"""
        url = "https://example.com/video.mp4"
        headers = {"Accept": "*/*"}

        content_info = ContentInfoResponse(
            status_code=404,
            content_type="",
            content_length=0,
            accept_ranges="",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        result = await content_processor._is_video_content(url, headers)

        assert result is False

    @pytest.mark.asyncio
    async def test_is_video_content_with_error_in_response(self, content_processor, mock_dependencies, caplog):
        """Тест проверки видео контента когда в ответе есть ошибка"""
        url = "https://example.com/video.mp4"
        headers = {"Accept": "*/*"}

        content_info = ContentInfoResponse(
            status_code=0,
            content_type="",
            content_length=0,
            accept_ranges="",
            headers={},
            method_used="HEAD",
            error="Connection timeout"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        with patch.object(content_processor, '_is_video_url', return_value=True):
            with caplog.at_level('WARNING'):
                result = await content_processor._is_video_content(url, headers)

            assert result is True
            assert "Error checking video content: Connection timeout" in caplog.text

    @pytest.mark.asyncio
    async def test_is_video_content_exception_handling(self, content_processor, mock_dependencies):
        """Тест обработки исключений при проверке видео контента"""
        url = "https://example.com/video.mp4"
        headers = {"Accept": "*/*"}

        mock_dependencies['content_getter'].get_content_info.side_effect = Exception("Network error")

        with patch.object(content_processor, '_is_video_url', return_value=False):
            result = await content_processor._is_video_content(url, headers)

            assert result is False

    @pytest.mark.asyncio
    async def test_is_video_content_small_file_with_range(self, content_processor, mock_dependencies):
        """Тест проверки маленького файла с поддержкой range"""
        url = "https://example.com/small.bin"
        headers = {"Accept": "*/*"}

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="application/octet-stream",
            content_length=100000,
            accept_ranges="bytes",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        with patch.object(content_processor, '_is_video_url', return_value=False):
            result = await content_processor._is_video_content(url, headers)

            assert result is False

    @pytest.mark.asyncio
    async def test_is_video_content_large_file_without_range(self, content_processor, mock_dependencies):
        """Тест проверки большого файла без поддержки range"""
        url = "https://example.com/large.bin"
        headers = {"Accept": "*/*"}

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="application/octet-stream",
            content_length=2000000,
            accept_ranges="none",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        with patch.object(content_processor, '_is_video_url', return_value=False):
            result = await content_processor._is_video_content(url, headers)

            assert result is False

    def test_is_video_url_by_extension(self, content_processor):
        """Тест проверки видео URL по расширению файла"""
        test_cases = [
            "https://example.com/video.mp4",
            "https://example.com/movie.avi",
            "https://example.com/film.mkv",
            "https://example.com/clip.mov"
        ]

        for url in test_cases:
            result = content_processor._is_video_url(url)
            assert result is True

    def test_is_video_url_by_pattern(self, content_processor):
        """Тест проверки видео URL по паттернам"""
        test_cases = [
            "https://example.com/api/video/stream123",
            "https://example.com/stream/live",
            "https://example.com/watch?video=true&id=123"
        ]

        for url in test_cases:
            result = content_processor._is_video_url(url)
            assert result is True

    def test_is_video_url_negative_cases(self, content_processor):
        """Тест отрицательных случаев проверки видео URL"""
        test_cases = [
            "https://example.com/image.jpg",
            "https://example.com/document.pdf",
            "https://example.com/audio.mp3",
            "https://example.com/api/data",
            "https://example.com/page.html"
        ]

        for url in test_cases:
            result = content_processor._is_video_url(url)
            assert result is False

    def test_is_video_url_empty_path(self, content_processor):
        """Тест проверки видео URL с пустым путем"""
        url = "https://example.com"

        result = content_processor._is_video_url(url)

        assert result is False

    def test_is_video_content_type_positive(self, content_processor):
        """Тест положительных случаев проверки content-type"""
        test_cases = [
            "video/mp4",
            "video/avi",
            "video/x-matroska",
            "video/quicktime",
            "application/video+mp4",
            "VIDEO/MP4"
        ]

        for content_type in test_cases:
            result = content_processor._is_video_content_type(content_type)
            assert result is True

    def test_is_video_content_type_negative(self, content_processor):
        """Тест отрицательных случаев проверки content-type"""
        test_cases = [
            "image/jpeg",
            "application/json",
            "text/html",
            "audio/mpeg",
            "",
            None
        ]

        for content_type in test_cases:
            result = content_processor._is_video_content_type(content_type)
            assert result is False

    def test_initialization(self, mock_dependencies):
        """Тест инициализации ContentProcessor"""
        processor = ContentProcessor(**mock_dependencies)

        assert processor.config == mock_dependencies['config']
        assert processor.http_factory == mock_dependencies['http_factory']
        assert processor.content_getter == mock_dependencies['content_getter']
        assert processor.video_streamer == mock_dependencies['video_streamer']
        assert processor.request_processor == mock_dependencies['request_processor']
        assert processor.logger.name == 'lampa-proxy-content-processor'

    @pytest.mark.asyncio
    async def test_process_content_logging(self, content_processor, mock_dependencies, caplog):
        """Тест логирования в process_content"""
        url = "https://example.com/video.mp4"

        content_processor._is_video_content = AsyncMock(return_value=True)
        mock_dependencies['video_streamer'].stream_video.return_value = Mock()

        with caplog.at_level('INFO'):
            await content_processor.process_content(url, 'GET')

        assert f"Processing GET content to: {url}" in caplog.text
        assert f"Video content detected, using streaming: {url}" in caplog.text

    @pytest.mark.asyncio
    async def test_is_video_content_logging(self, content_processor, mock_dependencies, caplog):
        """Тест логирования в _is_video_content"""
        url = "https://example.com/video.mp4"
        headers = {"Accept": "*/*"}

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="video/mp4",
            content_length=1024000,
            accept_ranges="bytes",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        with caplog.at_level('INFO'):
            result = await content_processor._is_video_content(url, headers)

        assert "Video detected by content-type: video/mp4" in caplog.text
        assert result is True

    @pytest.mark.asyncio
    async def test_is_video_content_octet_stream_logging(self, content_processor, mock_dependencies, caplog):
        """Тест логирования для octet-stream в _is_video_content"""
        url = "https://example.com/video.mp4"
        headers = {"Accept": "*/*"}

        content_info = ContentInfoResponse(
            status_code=200,
            content_type="application/octet-stream",
            content_length=1024000,
            accept_ranges="bytes",
            headers={},
            method_used="HEAD"
        )

        mock_dependencies['content_getter'].get_content_info.return_value = content_info

        with caplog.at_level('INFO'):
            result = await content_processor._is_video_content(url, headers)

        assert f"Video detected as octet-stream with video URL: {url}" in caplog.text
        assert result is True

    @pytest.mark.asyncio
    async def test_is_video_content_exception_logging(self, content_processor, mock_dependencies, caplog):
        """Тест логирования исключений в _is_video_content"""
        url = "https://example.com/video.mp4"
        headers = {"Accept": "*/*"}

        mock_dependencies['content_getter'].get_content_info.side_effect = Exception("Unexpected error")

        with caplog.at_level('WARNING'):
            with patch.object(content_processor, '_is_video_url', return_value=True):
                result = await content_processor._is_video_content(url, headers)

        assert "Error checking video content: Unexpected error" in caplog.text
        assert result is True