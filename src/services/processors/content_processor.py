import urllib.parse
from typing import Dict, Any

from src.models.responses import ContentInfoResponse
from src.utils.logger import get_logger
from src.models.interfaces import IContentProcessor, IConfig, IHttpClientFactory, IContentInfoGetter, IVideoStreamerProcessor, IRequestProcessor, Im3u8Processor


class ContentProcessor(IContentProcessor):
    """Основной процессор контента"""

    def __init__(self,
                 config: IConfig,
                 http_factory: IHttpClientFactory,
                 content_getter: IContentInfoGetter,
                 video_streamer: IVideoStreamerProcessor,
                 request_processor: IRequestProcessor,
                 m3u8_processor: Im3u8Processor):
        self.config = config
        self.http_factory = http_factory
        self.content_getter = content_getter
        self.video_streamer = video_streamer
        self.request_processor = request_processor
        self.m3u8_processor = m3u8_processor
        self.logger = get_logger('content-processor', self.config.log_level)

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

            content_info = await self._content_info(target_url,headers)
            if content_info:

                # Проверка на наличие файла в формате m3u8
                is_m3u8 = await self._is_m3u8_content(target_url, content_info)
                if is_m3u8:
                    return await self.m3u8_processor.process_request(
                        target_url, method, data,headers)

                # Проверка на наличие файла для потокового воспроизведения
                is_video = await self._is_video_content(target_url, content_info)
                if is_video:
                    return await self.video_streamer.stream_video(
                        target_url, headers, range_header)

        # Для не-GET запросов или не-видео контента используем обычный процессор
        async for result in self.request_processor.process_request(
            target_url,
            method,
            data,
            headers):
            return result

    async def _content_info(self, url: str, headers: Dict) -> bool | ContentInfoResponse:
        """Получение информации о контенте"""
        try:
            content_info = await self.content_getter.get_content_info(url, headers, use_head=True)

            if content_info.error:
                self.logger.warning(f"Error checking m3u8 content: {content_info.error}")
                return False

            if content_info.status_code not in [200, 206]:
                return False

            return content_info

        except Exception as e:
            self.logger.warning(f"Error checking m3u8 content: {str(e)}")
            return False

    async def _is_video_content(self, target_url: str, content_info:ContentInfoResponse) -> bool:
        """Улучшенная проверка видео контента с использованием HEAD запросов"""
        if not self._is_video_url(target_url):
            return False

        content_type = content_info.content_type.lower()

        # Проверяем content-type
        for indicator in self.config.video_indicators:
            if indicator in content_type:
                self.logger.info(f"Video detected by content-type: {content_type}")
                return True

        # Дополнительные проверки для специфических типов
        if 'octet-stream' in content_type and self._is_video_url(target_url):
            self.logger.info(f"Video detected as octet-stream with video URL: {target_url}")
            return True

        # Проверяем по другим заголовкам
        content_length = content_info.content_length
        accept_ranges = content_info.accept_ranges.lower()

        # Большие файлы с поддержкой range запросов могут быть видео
        if content_length > 1000000 and accept_ranges == 'bytes':
            self.logger.info(f"Possible video detected by size and range support: {content_length} bytes")
            return True

        return False

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

    async def _is_m3u8_content(self, target_url: str, content_info:ContentInfoResponse) -> bool:
        """Проверяет, является ли контент m3u8 плейлистом"""

        content_type = content_info.content_type.lower()

        m3u8_content_types = [
            'application/vnd.apple.mpegurl',
            'application/x-mpegurl',
            'audio/mpegurl',
            'audio/x-mpegurl'
        ]

        if any(m3u8_type in content_type for m3u8_type in m3u8_content_types):
            return True

        # Проверяем содержимое ответа на наличие признаков m3u8
        if hasattr(content_info, 'content') and content_info.content:
            content_sample = content_info.content[:1024].decode('utf-8', errors='ignore').lower()
            # M3U8 файлы обычно начинаются с #EXTM3U
            if content_sample.startswith('#extm3u'):
                return True

            # Или содержат типичные m3u8 теги
            m3u8_indicators = ['#ext-x-version:', '#ext-inf:', '#ext-x-targetduration:']
            if any(indicator in content_sample for indicator in m3u8_indicators):
                return True

        return False
