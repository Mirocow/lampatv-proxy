import os
import logging
from typing import List

from src.models.interfaces import IConfig


class AppConfig(IConfig):
    """Конфигурация приложения"""

    def __init__(self):
        self._log_level = os.getenv('LOG_LEVEL', 'WARNING').upper()
        self._setup_logging()

        self._timeout_connect = float(os.getenv('TIMEOUT_CONNECT', '10.0'))
        self._timeout_read = float(os.getenv('TIMEOUT_READ', '60.0'))
        self._timeout_write = float(os.getenv('TIMEOUT_WRITE', '10.0'))
        self._timeout_pool = float(os.getenv('TIMEOUT_POOL', '10.0'))

        self._use_proxy = os.getenv('USE_PROXY', 'false').lower() == 'true'
        self._user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        self._max_redirects = int(os.getenv('MAX_REDIRECTS', '5'))
        self._stream_chunk_size = int(os.getenv('STREAM_CHUNK_SIZE', '102400'))
        self._max_range_size = int(os.getenv('MAX_RANGE_SIZE', '104857600'))
        self._max_request_size = int(os.getenv('MAX_REQUEST_SIZE', '10485760'))
        self._proxy_test_url = os.getenv('PROXY_TEST_URL', 'http://httpbin.org/ip')
        self._proxy_test_timeout = int(os.getenv('PROXY_TEST_TIMEOUT', '10'))
        self._max_proxy_retries = int(os.getenv('MAX_PROXY_RETRIES', '3'))
        self._stream_timeout = float(os.getenv('STREAM_TIMEOUT', '60.0'))

        self._video_indicators = [
            'video/', 'application/x-mpegurl', 'application/vnd.apple.mpegurl',
            'application/dash+xml', 'application/vnd.ms-sstr+xml'
        ]

        self._video_extensions = [
            '.mp4', '.m4v', '.mkv', '.webm', '.flv', '.avi',
            '.mov', '.wmv', '.mpeg', '.mpg', '.3gp', '.m3u8', '.ts'
        ]

        self._video_patterns = [
            '/video/', '/stream/', '.m3u8', '.mpd', '/hls/', '/dash/',
            'index.m3u8', 'manifest.mpd', 'playlist.m3u8', 'hls.m3u8'
        ]

        self._video_content_types = [
            'video/mp4', 'video/mpeg', 'video/quicktime', 'video/x-msvideo',
            'video/x-flv', 'video/webm', 'video/3gpp', 'video/ogg',
            'application/x-mpegurl', 'application/vnd.apple.mpegurl',
            'video/mp2t', 'application/dash+xml'
        ]

        self._proxy_list = []
        self.load_proxy_list()

    def _setup_logging(self):
        logging.basicConfig(
            level=self._log_level,
            format='[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    def load_proxy_list(self):
        proxy_list_str = os.getenv('PROXY_LIST', '')
        if proxy_list_str:
            self._proxy_list = [
                p.strip()
                for p in proxy_list_str.split(',') if p.strip()
            ]

    def to_dict(self) -> dict:
        """Возвращает все параметры конфигурации в виде словаря"""
        result = {}
        try:
            # Пытаемся получить __dict__ экземпляра
            instance_dict = self.__dict__
            for key, value in instance_dict.items():
                if key.startswith('_') and not key.startswith('__'):
                    if not callable(value):
                        clean_key = key[1:]
                        result[clean_key] = value
        except (AttributeError, TypeError):
            # Если __dict__ недоступен, используем альтернативный подход
            return self._to_dict_fallback()

        return result

    def _to_dict_fallback(self) -> dict:
        """Альтернативный метод для случаев, когда __dict__ недоступен"""
        result = {}
        for attr_name in dir(self):
            if (attr_name.startswith('_') and
                not attr_name.startswith('__') and
                not attr_name.endswith('__')):
                try:
                    attr_value = getattr(self, attr_name)
                    if not callable(attr_value) and not isinstance(attr_value, type):
                        key = attr_name[1:]
                        result[key] = attr_value
                except (AttributeError, TypeError):
                    continue

        return result

    @property
    def log_level(self) -> str:
        return self._log_level

    @property
    def timeout_connect(self) -> float:
        return self._timeout_connect

    @property
    def timeout_read(self) -> float:
        return self._timeout_read

    @property
    def timeout_write(self) -> float:
        return self._timeout_write

    @property
    def timeout_pool(self) -> float:
        return self._timeout_pool

    @property
    def use_proxy(self) -> bool:
        return self._use_proxy

    @property
    def user_agent(self) -> str:
        return self._user_agent

    @property
    def max_redirects(self) -> int:
        return self._max_redirects

    @property
    def stream_chunk_size(self) -> int:
        return self._stream_chunk_size

    @property
    def max_range_size(self) -> int:
        return self._max_range_size

    @property
    def max_request_size(self) -> int:
        return self._max_request_size

    @property
    def proxy_test_url(self) -> str:
        return self._proxy_test_url

    @property
    def proxy_test_timeout(self) -> int:
        return self._proxy_test_timeout

    @property
    def max_proxy_retries(self) -> int:
        return self._max_proxy_retries

    @property
    def stream_timeout(self) -> float:
        return self._stream_timeout

    @property
    def video_indicators(self) -> List[str]:
        return self._video_indicators

    @property
    def video_extensions(self) -> List[str]:
        return self._video_extensions

    @property
    def video_patterns(self) -> List[str]:
        return self._video_patterns

    @property
    def video_content_types(self) -> List[str]:
        return self._video_content_types

    @property
    def proxy_list(self) -> List[str]:
        return self._proxy_list