import logging
import urllib.parse
from typing import Dict, Any

from src.models.interfaces import IContentProcessor, IConfig, IHttpClientFactory, IContentInfoGetter, IVideoStreamer, IRequestProcessor


class ContentProcessor(IContentProcessor):
    """Основной процессор контента"""

    def __init__(self, config: IConfig, http_factory: IHttpClientFactory,
                 content_getter: IContentInfoGetter, video_streamer: IVideoStreamer,
                 request_processor: IRequestProcessor):
        self.config = config
        self.http_factory = http_factory
        self.content_getter = content_getter
        self.video_streamer = video_streamer
        self.request_processor = request_processor
        self.logger = logging.getLogger('lampa-proxy-content-processor')

    async def process_content(self,
                           target_url: str,
                           method: str = 'GET',
                           data: Any = None,
                           headers: Dict = None,
                           range_header: str = None) -> Any:
        if headers is None:
            headers = {}

        self.logger.info(f"Processing {method} content to: {target_url}")

        if method.upper() == 'GET':
            is_video = await self._is_video_content(target_url, headers)
            if is_video:
                self.logger.info(f"Video content detected, using streaming: {target_url}")
                return await self.video_streamer.stream_video(target_url, headers, range_header)

        # Для не-GET запросов или не-видео контента используем обычный процессор
        async for result in self.request_processor.process_request(
            target_url,
            method,
            data,
            headers):
            return result

    async def _is_video_content(self, url: str, headers: Dict) -> bool:
        """Улучшенная проверка видео контента с использованием HEAD запросов"""
        if not self._is_video_url(url):
            return False

        try:
            content_info = await self.content_getter.get_content_info(url, headers, use_head=True)

            if content_info.error:
                self.logger.warning(f"Error checking video content: {content_info.error}")
                return self._is_video_url(url)

            if content_info.status_code not in [200, 206]:
                return False

            content_type = content_info.content_type.lower()

            # Проверяем content-type
            for indicator in self.config.video_indicators:
                if indicator in content_type:
                    self.logger.info(f"Video detected by content-type: {content_type}")
                    return True

            # Дополнительные проверки для специфических типов
            if 'octet-stream' in content_type and self._is_video_url(url):
                self.logger.info(f"Video detected as octet-stream with video URL: {url}")
                return True

            # Проверяем по другим заголовкам
            content_length = content_info.content_length
            accept_ranges = content_info.accept_ranges.lower()

            # Большие файлы с поддержкой range запросов могут быть видео
            if content_length > 1000000 and accept_ranges == 'bytes':
                self.logger.info(f"Possible video detected by size and range support: {content_length} bytes")
                return True

            return False

        except Exception as e:
            self.logger.warning(f"Error checking video content: {str(e)}")
            return self._is_video_url(url)

    def _is_video_url(self, url: str) -> bool:
        """Проверяет, является ли URL видеофайлом по расширению и паттернам"""
        url_lower = url.lower()
        url_parts = urllib.parse.urlparse(url_lower)

        # Проверяем расширения файлов
        if url_parts.path and any(url_parts.path.endswith(ext) for ext in self.config.video_extensions):
            return True

        return any(pattern in url_lower for pattern in self.config.video_patterns)

    def _is_video_content_type(self, content_type: str) -> bool:
        if not content_type:
            return False
        content_type_lower = content_type.lower()
        return any(indicator in content_type_lower for indicator in self.config.video_indicators)
