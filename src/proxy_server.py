#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import base64
import json
import logging
import urllib.parse
import re
import os
from datetime import datetime
from typing import Dict, Optional, Tuple, Union, List
from contextlib import asynccontextmanager

import uvicorn
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from src.proxy_manager import ProxyManager

# ==================== Configuration ====================

# Конфигурация логирования
log_level = os.getenv('LOG_LEVEL', 'WARNING').upper()
logging.basicConfig(
    level=log_level,
    format='[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('lampa-proxy')

app = FastAPI(
    title="Lampa Proxy Server",
    description="Прокси сервер с поддержкой потокового видео, Range запросов и перемотки",
    version="3.2.1"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация
CONFIG = {
    'timeout': 30.0,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'max_redirects': int(os.getenv('MAX_REDIRECTS', '5')),
    'use_proxy': os.getenv('USE_PROXY', 'false').lower() == 'true',
    'proxy_list': [],
    'working_proxies': [],
    'proxy_test_url': os.getenv('PROXY_TEST_URL', 'http://httpbin.org/ip'),
    'proxy_test_timeout': int(os.getenv('PROXY_TEST_TIMEOUT', '10')),
    'max_proxy_retries': int(os.getenv('MAX_PROXY_RETRIES', '3')),
    'stream_chunk_size': int(os.getenv('STREAM_CHUNK_SIZE', '102400')),
    'stream_timeout': float(os.getenv('STREAM_TIMEOUT', '60.0')),
    'video_content_types': [
        'video/mp4', 'video/mpeg', 'video/quicktime', 'video/x-msvideo',
        'video/x-flv', 'video/webm', 'video/3gpp', 'video/ogg',
        'application/x-mpegurl', 'application/vnd.apple.mpegurl',
        'video/mp2t', 'application/dash+xml'
    ],
    # Явные настройки таймаутов
    'timeout_connect': float(os.getenv('TIMEOUT_CONNECT', '10.0')),
    'timeout_read': float(os.getenv('TIMEOUT_READ', '60.0')),
    'timeout_write': float(os.getenv('TIMEOUT_WRITE', '10.0')),
    'timeout_pool': float(os.getenv('TIMEOUT_POOL', '10.0')),
    'max_range_size': int(os.getenv('MAX_RANGE_SIZE', '104857600')),
    'max_request_size': int(os.getenv('MAX_REQUEST_SIZE', '10485760')),
    # Таймаут для HEAD запросов
    'head_request_timeout': float(os.getenv('HEAD_REQUEST_TIMEOUT', '15.0')),
}

# Инициализация менеджера прокси
proxy_manager = ProxyManager()


def load_proxy_list():
    """Загрузка списка прокси из переменных окружения"""
    proxy_list_str = os.getenv('PROXY_LIST', '')
    if proxy_list_str:
        CONFIG['proxy_list'] = [
            p.strip()
            for p in proxy_list_str.split(',') if p.strip()
        ]


@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске приложения"""
    load_proxy_list()

    if CONFIG['use_proxy'] and CONFIG['proxy_list']:
        logger.info("Starting proxy validation...")
        working_proxies = await proxy_manager.validate_proxies(CONFIG['proxy_list'])

        for proxy in working_proxies:
            await proxy_manager.add_proxy(proxy)
        logger.info(f"Loaded {len(working_proxies)} working proxies")

# ==================== Enhanced Video Detection with HEAD Requests ====================


async def is_video_content(url: str, headers: Dict = None) -> Tuple[bool, Dict]:
    """
    Проверяет, является ли контент видео используя HEAD запрос для получения точной информации.
    Возвращает кортеж (is_video: bool, content_info: Dict)
    """
    if headers is None:
        headers = {}

    # Сначала проверяем по URL для быстрой фильтрации
    if not is_video_url(url):
        return False, {}

    try:
        # Получаем информацию о контенте через HEAD запрос
        content_info = await get_content_info(url, headers, use_head=True)

        content_type = content_info.get('content_type', '').lower()
        status_code = content_info.get('status_code', 0)

        # Проверяем статус код
        if status_code not in [200, 206]:
            return False, content_info

        # Проверяем content-type
        video_indicators = [
            'video/', 'application/x-mpegurl', 'application/vnd.apple.mpegurl',
            'application/dash+xml', 'application/vnd.ms-sstr+xml'
        ]

        for indicator in video_indicators:
            if indicator in content_type:
                logger.info(f"Video detected by content-type: {content_type}")
                return True, content_info

        # Дополнительные проверки для специфических типов
        if 'octet-stream' in content_type and is_video_url(url):
            logger.info(
                f"Video detected as octet-stream with video URL: {url}")
            return True, content_info

        # Проверяем по другим заголовкам
        content_length = content_info.get('content_length', 0)
        accept_ranges = content_info.get('accept_ranges', '').lower()

        # Большие файлы с поддержкой range запросов могут быть видео
        if content_length > 1000000 and accept_ranges == 'bytes':
            logger.info(
                f"Possible video detected by size and range support: {content_length} bytes")
            return True, content_info

        return False, content_info

    except Exception as e:
        logger.warning(f"Error checking video content via HEAD: {e}")
        # При ошибке возвращаем предположительный результат на основе URL
        return is_video_url(url), {}


def is_video_url(url: str) -> bool:
    """Проверяет, является ли URL видеофайлом по расширению"""
    video_extensions = ['.mp4', '.m4v', '.mkv', '.webm', '.flv', '.avi',
                        '.mov', '.wmv', '.mpeg', '.mpg', '.3gp', '.m3u8', '.ts']
    url_lower = url.lower()

    url_parts = urllib.parse.urlparse(url_lower)

    # Проверяем расширения файлов
    if url_parts.path and any(url_parts.path.endswith(ext) for ext in video_extensions):
        return True

    # Проверяем паттерны в URL для видео стримов
    video_patterns = [
        '/video/', '/stream/', '.m3u8', '.mpd', '/hls/', '/dash/',
        'index.m3u8', 'manifest.mpd', 'playlist.m3u8', 'hls.m3u8'
    ]

    return any(pattern in url_lower for pattern in video_patterns)


async def get_content_info(url: str, headers: Dict, use_head: bool = True) -> Dict:
    """
    Получает точную информацию о контенте, гарантированно определяя длину файла.
    Использует комбинацию HEAD и GET запросов с различными стратегиями.
    """
    # Для видеофайлов увеличиваем таймауты
    is_video_url_check = is_video_url(url)
    timeout_multiplier = 2.0 if is_video_url_check else 1.0

    timeout = httpx.Timeout(
        connect=CONFIG['timeout_connect'] * timeout_multiplier,
        read=CONFIG['head_request_timeout'] * timeout_multiplier,
        write=CONFIG['timeout_write'] * timeout_multiplier,
        pool=CONFIG['timeout_pool'] * timeout_multiplier
    )

    client_params = {
        'headers': headers,
        'timeout': timeout,
        'follow_redirects': True
    }

    # Добавляем прокси если доступен
    if CONFIG['use_proxy'] and proxy_manager.working_proxies:
        proxy = proxy_manager.get_random_proxy()
        if proxy:
            client_params['proxy'] = proxy
            logger.info(f"Using proxy for streaming: {proxy}")

    client = None
    try:
        client = httpx.AsyncClient(**client_params)

        content_length = 0
        content_type = 'application/octet-stream'
        accept_ranges = 'bytes'
        status_code = 0
        response_headers = {}
        method_used = 'ERROR'

        # Сначала пробуем HEAD запрос для быстрого определения
        if use_head:
            try:
                logger.debug(f"Trying HEAD request for: {url}")
                response = await client.head(url)
                status_code = response.status_code
                response_headers = dict(response.headers)
                method_used = 'HEAD'
                content_type = response.headers.get('content-type', '')
                accept_ranges = response.headers.get('accept-ranges', 'bytes')

                # Пробуем получить размер из Content-Length
                if response.headers.get('content-length'):
                    try:
                        content_length = int(
                            response.headers.get('content-length'))
                        logger.debug(
                            f"Got content length from HEAD: {content_length}")

                        return {
                            'status_code': status_code,
                            'content_type': content_type,
                            'content_length': content_length,
                            'accept_ranges': accept_ranges,
                            'headers': response_headers,
                            'method_used': method_used
                        }

                    except (ValueError, TypeError) as e:
                        logger.warning(
                            f"Invalid Content-Length from HEAD: {e}")
                        content_length = 0

            except Exception as e:
                logger.warning(f"HEAD request failed: {e}")

        # Если HEAD не сработал или не дал длину, пробуем GET с Range
        strategies = [
            # Стратегия 1: Range запрос для получения Content-Range
            {'Range': 'bytes=0-0', 'description': 'Range 0-0'},

            # Стратегия 2: Range запрос для больших диапазонов (если сервер требует)
            {'Range': 'bytes=0-999', 'description': 'Range 0-999'},

            # Стратегия 3: Без Range (последняя попытка)
            {},  # Пустые headers для обычного GET
        ]

        for strategy in strategies:
            try:
                strategy_headers = headers.copy()
                strategy_headers.update(strategy)

                logger.debug(
                    f"Trying GET with strategy: {strategy.get('description', 'Simple GET')}")

                async with client.stream('GET', url, headers=strategy_headers) as response:
                    status_code = response.status_code
                    response_headers = dict(response.headers)
                    method_used = f"GET_{strategy.get('description', 'SIMPLE')}"

                    # Обновляем информацию из заголовков
                    if not content_type:
                        content_type = response.headers.get('content-type', '')

                    accept_ranges = response.headers.get(
                        'accept-ranges', accept_ranges)

                    # Приоритет 1: Content-Range (самый надежный для определения полной длины)
                    if response.status_code == 206 and 'content-range' in response.headers:
                        content_range = response.headers['content-range']

                        # Парсим форматы: "bytes 0-100/123456" или "bytes */123456"
                        match = re.match(
                            r'bytes\s+\*?/?(\d+)-?(\d+)?/(\d+)', content_range)

                        if match:
                            total_size = match.group(3)
                            content_length = int(total_size)
                            logger.debug(
                                f"Got content length from Content-Range: {content_length}")
                            break

                    # Приоритет 2: Content-Length из частичного контента
                    elif response.status_code == 206 and response.headers.get('content-length'):
                        # Для частичного контента Content-Length показывает размер части,
                        # но мы можем использовать его если других вариантов нет
                        try:
                            partial_length = int(
                                response.headers.get('content-length'))
                            logger.debug(
                                f"Got partial content length: {partial_length}")

                            # Если это маленький кусок, продолжаем поиск полной длины
                            if partial_length < 1000:
                                continue

                        except (ValueError, TypeError):
                            pass

                    # Приоритет 3: Content-Length из полного ответа
                    elif response.status_code == 200 and response.headers.get('content-length'):
                        try:
                            content_length = int(
                                response.headers.get('content-length'))
                            logger.debug(
                                f"Got content length from full GET: {content_length}")
                            break

                        except (ValueError, TypeError) as e:
                            logger.warning(
                                f"Invalid Content-Length from GET: {e}")

                    # Читаем немного данных чтобы убедиться в работе соединения
                    try:
                        chunk = await response.read(1024)  # Читаем 1KB
                        if chunk and response.status_code == 200 and not content_length:
                            logger.debug(
                                "Got data chunk but no content length available")

                    except Exception as e:
                        logger.debug(f"Error reading chunk: {e}")

            except Exception as e:
                logger.warning(f"GET strategy failed: {e}")
                continue

        # Если все стратегии не дали результат, логируем проблему
        if content_length == 0:
            logger.warning(f"Could not determine content length for: {url}")

        return {
            'status_code': status_code,
            'content_type': content_type,
            'content_length': content_length,
            'accept_ranges': accept_ranges,
            'headers': response_headers,
            'method_used': method_used
        }

    except Exception as e:
        logger.error(f"Failed to get content info: {e}")
        return {
            'status_code': 0,
            'content_type': 'application/octet-stream',
            'content_length': 0,
            'accept_ranges': 'bytes',
            'error': str(e),
            'method_used': 'ERROR'
        }

    finally:
        if client:
            await client.aclose()


async def is_stream_complete(response: httpx.Response, bytes_streamed: int, expected_bytes: int) -> bool:
    """Определяет, завершен ли видео-поток"""
    if expected_bytes > 0 and bytes_streamed >= expected_bytes:
        return True

    # Для неизвестного размера полагаемся на завершение соединения
    if response.status_code == 200 and expected_bytes == 0:
        return False  # Пусть клиент определяет конец

    return False


async def stream_video_with_range(
    target_url: str,
    request_headers: Dict,
    range_header: str = None
) -> Response:
    """Потоковая передача видео с поддержкой Range запросов для перемотки"""

    logger.info(f"Streaming video with range support from: {target_url}")
    logger.debug(f"Range header: {range_header}")

    # Подготавливаем заголовки для исходного сервера
    headers = {
        'User-Agent': CONFIG['user_agent'],
        'Accept': '*/*',
        'Accept-Encoding': 'identity',  # Отключаем сжатие для точного позиционирования
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,ru;q=0.7',
    }

    # Добавляем пользовательские заголовки (исключая конфликтующие)
    if request_headers:
        headers.update({k: v for k, v in request_headers.items()
                       if k.lower() not in ['host', 'content-length', 'range', 'accept-encoding']})

    # Получаем точную информацию о контенте с использованием HEAD запроса
    try:
        content_info = await get_content_info(target_url, headers, use_head=True)
        logger.info(
            f"Content info: status={content_info['status_code']}, size={content_info['content_length']}, type={content_info['content_type']}")

    except Exception as e:
        logger.error(f"Failed to get content info: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get video info: {str(e)}")

    file_size = content_info['content_length']
    content_type = content_info['content_type']

    # Если размер файла неизвестен, логируем предупреждение
    if file_size == 0:
        logger.warning(
            "File size is unknown, range requests may not work properly")

    # Парсим Range заголовок
    start_byte, end_byte = parse_range_header(range_header, file_size)
    logger.info(
        f"Requested range: {start_byte}-{end_byte} (file size: {file_size})")

    # Устанавливаем Range заголовок для исходного сервера
    range_requested = False
    if range_header or start_byte > 0 or (file_size > 0 and end_byte < file_size - 1):
        if file_size > 0:
            headers['Range'] = f'bytes={start_byte}-{end_byte}'
        else:
            # Для неизвестного размера запрашиваем с начальной позиции
            headers['Range'] = f'bytes={start_byte}-'
        range_requested = True
        logger.info(f"Sending Range to source: {headers['Range']}")

    # Создаем timeout с увеличенными значениями для видео
    timeout = httpx.Timeout(
        connect=CONFIG['timeout_connect'],
        read=300.0,  # Увеличиваем таймаут для длинных видео
        write=CONFIG['timeout_write'],
        pool=CONFIG['timeout_pool']
    )

    client_params = {
        'headers': headers,
        'timeout': timeout,
        'follow_redirects': True,
        'verify': False  # Отключаем проверку SSL для большей совместимости
    }

    # Добавляем прокси если доступен
    if CONFIG['use_proxy'] and proxy_manager.working_proxies:
        proxy = proxy_manager.get_random_proxy()
        if proxy:
            client_params['proxy'] = proxy
            logger.info(f"Using proxy for streaming: {proxy}")

    async def video_stream_generator():
        """Генератор для потоковой передачи видео данных"""
        client = None
        stream_active = True
        bytes_streamed = 0

        try:
            client = httpx.AsyncClient(**client_params)

            async with client.stream('GET', target_url) as response:
                logger.info(f"Source response status: {response.status_code}")

                # Проверяем статус ответа
                if response.status_code == 404:
                    logger.error(f"Video not found (404): {target_url}")
                    stream_active = False
                    return

                elif response.status_code == 416:  # Range Not Satisfiable
                    logger.error(f"Range not satisfiable (416): {target_url}")
                    stream_active = False
                    return

                elif response.status_code >= 400:
                    logger.error(
                        f"Source server error {response.status_code}: {target_url}")
                    stream_active = False
                    return

                # Логируем информацию о ответе
                response_content_type = response.headers.get(
                    'content-type', '')
                content_range = response.headers.get('content-range', '')
                response_content_length = response.headers.get(
                    'content-length', 'unknown')

                logger.info(f"Video content-type: {response_content_type}")
                logger.info(f"Content-Range: {content_range}")
                logger.info(f"Content-Length: {response_content_length}")

                # Определяем ожидаемое количество байт
                expected_bytes = 0
                if content_range:
                    # Парсим Content-Range: bytes start-end/total
                    match = re.match(
                        r'bytes\s+(\d+)-(\d+)/(\d+)', content_range)
                    if match:
                        range_start = int(match.group(1))
                        range_end = int(match.group(2))
                        expected_bytes = range_end - range_start + 1
                        logger.info(
                            f"Expected bytes from Content-Range: {expected_bytes}")

                elif response_content_length != 'unknown':
                    try:
                        expected_bytes = int(response_content_length)
                        logger.info(
                            f"Expected bytes from Content-Length: {expected_bytes}")

                    except ValueError:
                        expected_bytes = 0

                # Читаем и передаем данные чанками
                async for chunk in response.aiter_bytes(chunk_size=CONFIG['stream_chunk_size']):
                    if not stream_active:
                        break

                    bytes_streamed += len(chunk)
                    logger.debug(f"Streamed {bytes_streamed} bytes so far")

                    # Проверяем, не достигли ли мы ожидаемого конца
                    if expected_bytes > 0 and bytes_streamed >= expected_bytes:
                        logger.info(
                            f"Reached expected end of stream: {bytes_streamed}/{expected_bytes} bytes")
                        yield chunk
                        break

                    yield chunk

                logger.info(
                    f"Video stream completed: {bytes_streamed} bytes streamed")

        except asyncio.CancelledError:
            logger.info("Video stream was cancelled by client")
            stream_active = False

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error during video streaming: {e.response.status_code}")
            stream_active = False

        except httpx.TimeoutException:
            logger.error(f"Video stream timeout: {target_url}")
            stream_active = False

        except httpx.RequestError as e:
            logger.error(f"Video stream request error: {str(e)}")
            stream_active = False

        except Exception as e:
            logger.error(f"Unexpected video stream error: {str(e)}")
            stream_active = False

        finally:
            # Аккуратно закрываем клиент
            if client:
                try:
                    await client.aclose()

                except Exception as e:
                    logger.debug(f"Error closing client: {e}")

    # Подготавливаем заголовки ответа
    response_headers = {
        'Accept-Ranges': 'bytes',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': '*',
        'Access-Control-Expose-Headers': 'Content-Length, Content-Range, Accept-Ranges',
        'Content-Type': content_type,
        'X-Content-Type-Options': 'nosniff',
    }

    # Определяем статус код и дополнительные заголовки
    if range_requested:
        status_code = 206  # Partial Content

        if file_size > 0:
            content_length = end_byte - start_byte + 1
            response_headers['Content-Range'] = f'bytes {start_byte}-{end_byte}/{file_size}'
            response_headers['Content-Length'] = str(content_length)
            logger.info(
                f"Sending 206 Partial Content: {content_length} bytes (range: {start_byte}-{end_byte})")
        else:
            # Если размер неизвестен, не указываем Content-Length и Content-Range
            # Это позволяет плееру корректно определять конец видео
            logger.info(
                "Sending 206 Partial Content without Content-Range (unknown file size)")

    else:
        status_code = 200  # OK
        if file_size > 0:
            response_headers['Content-Length'] = str(file_size)
            logger.info(f"Sending 200 OK: {file_size} bytes")
        else:
            logger.info("Sending 200 OK with unknown file size")

    return StreamingResponse(
        video_stream_generator(),
        media_type=content_type,
        headers=response_headers,
        status_code=status_code
    )


def parse_range_header(range_header: Optional[str], file_size: int) -> Tuple[int, int]:
    """Парсит заголовок Range и возвращает начальный и конечный байты"""
    if not range_header:
        return 0, file_size - 1 if file_size > 0 else 0

    try:
        # Формат: bytes=start-end
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if not range_match:
            return 0, file_size - 1 if file_size > 0 else 0

        start = int(range_match.group(1))
        end_str = range_match.group(2)

        if end_str:
            end = int(end_str)
        else:
            # Если конец не указан, используем до конца файла
            end = file_size - 1 if file_size > 0 else 0

        # Валидация диапазона
        if file_size > 0:
            if start < 0:
                start = 0
            if start >= file_size:
                # Если начало после конца файла, возвращаем пустой диапазон
                start = file_size - 1
                end = file_size - 1
            if end >= file_size:
                end = file_size - 1
            if start > end:
                start, end = end, start  # Корректируем если начало после конца

        # Ограничиваем максимальный размер диапазона
        if file_size > 0 and (end - start) > CONFIG['max_range_size']:
            end = start + CONFIG['max_range_size'] - 1
            if end >= file_size:
                end = file_size - 1

        logger.debug(f"Parsed range: {start}-{end} (file size: {file_size})")
        return start, end

    except Exception as e:
        logger.error(f"Error parsing range header '{range_header}': {e}")
        return 0, file_size - 1 if file_size > 0 else 0

# ==================== Core Functions ====================


def decode_base64_url(encoded_str: str) -> str:
    """Декодирование base64 URL с обработкой ошибок"""
    try:
        decoded_url = urllib.parse.unquote(encoded_str)
        # Добавляем padding если необходимо
        padding = 4 - len(decoded_url) % 4
        if padding != 4:
            decoded_url += '=' * padding
        decoded_bytes = base64.b64decode(decoded_url)
        result = decoded_bytes.decode('utf-8')
        logger.debug(f"Successfully decoded base64: {result[:100]}...")
        return result

    except Exception as e:
        raise e
        # logger.error(f"Base64 decoding error: {encoded_str}, error: {str(e)}")
        # raise ValueError(f"Base64 decoding error: {str(e)}")


def normalize_url(url: str) -> str:
    """Нормализация URL и исправление проблем с протоколом"""
    if not url:
        raise ValueError("Empty URL")

    logger.debug(f"Original URL for normalization: {url}")

    # Убираем дублирующиеся протоколы
    protocols = ['https://', 'http://']
    for proto1 in protocols:
        for proto2 in protocols:
            duplicate = proto1 + proto2
            if url.startswith(duplicate):
                url = url[len(proto1):]
                logger.debug(f"Removed duplicate protocol: {url}")
                break

    # Обрабатываем protocol-relative URLs (начинающиеся с //)
    if url.startswith('//'):
        url = 'https:' + url
        logger.debug(f"Fixed protocol-relative URL: {url}")

    # Исправляем неправильные слеши
    url = re.sub(r'(https?:/)([^/])', r'\1/\2', url)

    # Добавляем протокол если отсутствует
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    logger.debug(f"Normalized URL: {url}")
    return url


def parse_encoded_data(encoded_str):# -> tuple[dict, list]:
    """Парсинг закодированных данных в формате prox_enc"""
    params = {}
    url = []

    if not encoded_str:
        return params, url
    
    # Разделяем строку по символу '/'
    parts = encoded_str.split('/')
    
    i = 0
    n= 0

    # Обрабатываем части последовательно
    while i < len(parts):
        # Если находим "param", то следующий элемент должен быть в формате "ключ=значение"
        if parts[i] == 'param' and i + 1 < len(parts):
            key_value = parts[i + 1]
            if '=' in key_value:
                key, value = key_value.split('=', 1)
                # Декодируем URL-encoded значение
                decoded_value = urllib.parse.unquote(value)
                params[key] = decoded_value
                i += 2 # Пропускаем два элемента: 'param' и 'ключ=значение'
                n = i
                continue
            
        i += 1
    
    return params, parts[n:]


def build_url(segments, query_params=None):
    """Построение целевого URL из сегментов с возможностью добавления query-параметров"""
    if not segments:
        raise ValueError("No URL segments provided")

    url = '/'.join(segments)
    logger.debug(f"Joined URL from segments: {url}")

    url_match = re.search(r'(https?://[^\s]+)', url)
    if url_match:
        url = url_match.group(1)
        logger.debug(f"Extracted URL: {url}")
    else:
        url = normalize_url(url)

    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"Invalid hostname in URL: {url}")

    # Добавляем query-параметры если они переданы
    if query_params:
        # Если query_params передан как список кортежей
        if isinstance(query_params, list) and all(isinstance(item, (list, tuple)) for item in query_params):
            query_string = urllib.parse.urlencode(query_params)
        # Если query_params передан как словарь
        elif isinstance(query_params, dict):
            query_string = urllib.parse.urlencode(query_params)
        else:
            raise ValueError(
                "query_params must be a dictionary or list of tuples")

        # Объединяем существующие query-параметры с новыми
        current_query = parsed.query
        if current_query:
            new_query = f"{current_query}&{query_string}"
        else:
            new_query = query_string

        # Собираем URL с новыми параметрами
        parsed = parsed._replace(query=new_query)
        url = urllib.parse.urlunparse(parsed)

    return url


async def handle_redirect(response, original_headers, method, data, redirect_count=0):
    """Обработка HTTP редиректов автоматически"""
    if redirect_count >= CONFIG['max_redirects']:
        raise ValueError(
            f"Too many redirects (max: {CONFIG['max_redirects']})")

    if 'location' not in response.headers:
        raise ValueError("Redirect response without Location header")

    redirect_url = response.headers['location']
    logger.info(f"Following redirect {redirect_count + 1} to: {redirect_url}")

    if not redirect_url.startswith(('http://', 'https://')):
        parsed_original = urllib.parse.urlparse(str(response.url))
        base_url = f"{parsed_original.scheme}://{parsed_original.netloc}"
        redirect_url = urllib.parse.urljoin(base_url, redirect_url)

    return await make_request(redirect_url, method, data, original_headers, redirect_count + 1)


def is_valid_json(text):
    """Проверка валидности JSON включая примитивы"""
    if not text:
        return False

    text = text.strip()
    if not text:
        return False

    # # Явно проверяем JSON примитивы
    # if text in ['null', 'true', 'false']:
    #     return True

    # # Проверяем числа
    # if text.isdigit() or (text.startswith('-') and text[1:].isdigit()):
    #     return True

    # Стандартная проверка JSON
    if (text.startswith('{') and text.endswith('}')) or (text.startswith('[') and text.endswith(']')):
        try:
            json.loads(text)
            return True
        except (json.JSONDecodeError, ValueError):
            return False

    return False


async def make_request_with_proxy(target_url, method='GET', data=None, headers=None, retry_count=0):
    """Выполнение запроса через прокси с повторными попытками"""
    proxy = proxy_manager.get_random_proxy()

    if not proxy:
        logger.warning("No working proxies available, making direct request")
        return await make_direct_request(target_url, method, data, headers)

    try:
        result = await make_direct_request(target_url, method, data, headers, proxy)
        await proxy_manager.mark_proxy_success(proxy)
        return result

    except Exception as e:
        logger.error(f"✕ Request through proxy {proxy} failed: {str(e)}")
        await proxy_manager.mark_proxy_failure(proxy)

        if retry_count < CONFIG['max_proxy_retries']:
            logger.info(
                f"Retrying request with different proxy (attempt {retry_count + 1})")
            return await make_request_with_proxy(target_url, method, data, headers, retry_count + 1)
        else:
            logger.error(
                "All proxy attempts failed, falling back to direct request")
            return await make_direct_request(target_url, method, data, headers)


async def make_direct_request(target_url, method='GET', data=None, headers=None, proxy=None):
    """Выполнение HTTP запроса напрямую или через указанный прокси"""
    logger.info(f"Making {method} request to: {target_url}, proxy: {proxy}")
    logger.debug(f"Request data type: {type(data)}, length: {len(data) if data else 0}")

    target_url = normalize_url(target_url)

    try:
        parsed = urllib.parse.urlparse(target_url)
        if not parsed.hostname:
            raise ValueError(f"Invalid hostname: {target_url}")

        request_headers = {
            'User-Agent': CONFIG['user_agent'],
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,ru;q=0.7',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }

        # Добавляем пользовательские заголовки
        if headers:
            request_headers.update(headers)

        # Исправление: создаем timeout с явными параметрами
        timeout_config = httpx.Timeout(
            connect=CONFIG['timeout_connect'],
            read=CONFIG['timeout_read'],
            write=CONFIG['timeout_write'],
            pool=CONFIG['timeout_pool']
        )

        # Настройки для запроса
        init_params = {
            'headers': request_headers,
            'follow_redirects': False,
            'timeout': timeout_config
        }

        # Добавляем прокси если указан
        if proxy:
            init_params['proxy'] = proxy
            # Исправление: явно задаем все параметры таймаута для прокси
            init_params['timeout'] = httpx.Timeout(
                connect=300.0,
                read=300.0,
                write=300.0,
                pool=300.0
            )
            logger.info(f"✓ Using proxy: {proxy}")

        # Для POST, PUT, DELETE запросов data передается как тело запроса
        request_params = {}
        if method.upper() in ['POST', 'PUT', 'DELETE'] and data:
            if isinstance(data, dict):
                request_params['data'] = data
            else:
                request_params['content'] = data

        async with httpx.AsyncClient(**init_params) as client:
            response = await client.request(method, target_url, **request_params)

        logger.info(f"Response status: {response.status_code}")

        # Обрабатываем редиректы
        if response.status_code in [301, 302, 303, 307, 308]:
            logger.info(f"Redirect detected: {response.status_code}")
            return await handle_redirect(response, request_headers, method, data)

        # Собираем cookies
        cookies = []
        resp_headers = {}
        for name, value in response.headers.multi_items():
            name_lower = name.lower()
            if name_lower == 'set-cookie':
                cookies.append(value)
            resp_headers[name_lower] = value

        resp_headers['set-cookie'] = cookies

        return {
            'currentUrl': str(response.url),
            'cookie': cookies,
            'headers': resp_headers,
            'status': response.status_code,
            'body': response.text
        }

    except httpx.TimeoutException:
        logger.error(f"✕ Request timeout: {target_url}")
        return {
            'error': 'Request timeout',
            'body': '',
            'headers': {},
            'status': 408
        }
    except httpx.RequestError as e:
        logger.error(f"✕ Request failed: {target_url} - {str(e)}")
        return {
            'error': f'Request failed: {str(e)}',
            'body': '',
            'headers': {},
            'status': 500
        }
    except Exception as e:
        logger.error(f"✕ Unexpected error: {target_url} - {str(e)}")
        return {
            'error': f'Unexpected error: {str(e)}',
            'body': '',
            'headers': {},
            'status': 500
        }


async def make_request(target_url, method='GET', data=None, headers=None, redirect_count=0):
    """Основная функция выполнения запроса"""
    if CONFIG['use_proxy'] and proxy_manager.working_proxies:
        return await make_request_with_proxy(target_url, method, data, headers)
    else:
        return await make_direct_request(target_url, method, data, headers)

# ==================== Request Handlers ====================


async def handle_encoded_request(segments, method='GET', post_data=None, query_params=None, request_headers=None):
    """Обработка закодированных запросов (enc/enc1/enc2/enc3)"""
    logger.info(
        f"Processing encoded {method} request with {len(segments)} segments")

    if len(segments) < 2:
        raise ValueError("Invalid encoded request - not enough segments")

    encoded_part = segments[1]
    additional_segments = segments[2:]
    handler_type = segments[0]

    # Декодируем base64 данные
    decoded_data = decode_base64_url(encoded_part)
    logger.info(f"Decoded data: {decoded_data} from encoded: {handler_type}")

    # Парсим параметры из декодированных данных
    encoded_params, url_segments_from_encoded = parse_encoded_data(decoded_data)

    # Определяем целевой URL в зависимости от типа кодирования
    target_url = ""

    if handler_type in ['enc', 'enc1', 'enc3']:
        if not additional_segments:
            raise ValueError("No URL found in encoded data for enc")

        if encoded_params:
            for key in ['User-Agent', 'Origin', 'Referer', 'Cookie', 'Content-Type', 'Accept',
                        'x-csrf-token', 'Sec-Fetch-Dest', 'Sec-Fetch-Mode', 'Sec-Fetch-Site', 'Authorization', 'Range']:
                if key in encoded_params:
                    request_headers[key] = encoded_params[key]

        target_url = build_url(additional_segments, query_params)

    elif handler_type == 'enc2':
        if not url_segments_from_encoded:
            raise ValueError("No URL found in encoded data for enc2")

        for param in additional_segments:
            try:
                # Декодируем base64 данные
                decoded_data = decode_base64_url(param)
                if decoded_data:
                    # Безопасное разбиение на параметры
                    new_params = {}
                    for pair in decoded_data.split('&'):
                        if '=' in pair:
                            key, value = pair.split('=', 1)
                            new_params[key] = value
                        else:
                            # Обработка параметров без значения
                            new_params[pair] = None

                    query_params = {**query_params, **new_params}

            except Exception as e:
                continue

        target_url = build_url(url_segments_from_encoded, query_params)

    logger.info(f"Proxying {method} with encode type {handler_type} request to: {target_url}")

    # Улучшенная проверка видео с использованием HEAD запроса
    is_video = False
    content_info = {}

    # Проверка на наличие стрима
    if method.upper() == 'GET':
        is_video, content_info = await is_video_content(target_url, request_headers)

    if is_video:
        logger.info(f"Video content detected, using streaming: {target_url}")
        range_header = request_headers.get('Range') if request_headers else None
        return await stream_video_with_range(target_url, request_headers, range_header), 200, ''

    # Отправка запроса на проксирующий сервер
    response = await make_request(
        target_url,
        method,
        post_data,
        request_headers)

    # Если ответ уже StreamingResponse (для видео), возвращаем как есть
    if isinstance(response, StreamingResponse):
        return response, 200, ''

    response_content_type = response.get(
        'headers', {}).get('content-type', '').lower()

    if handler_type in ['enc', 'enc1', 'enc2']:
        response_body = response.get('body')
        if 'application/json' in response_content_type and is_valid_json(response_body):
            response_body = json.loads(response_body)

    elif handler_type == 'enc3':
        if 'text/html' in response_content_type or 'text/plain' in response_content_type and is_valid_json(response):
            response_content_type = 'application/json'
            response_body = response

        elif 'application/json' in response_content_type:
            response_body = response

    return response_body if 'response_body' in locals() else response.get('body'), response.get('status', 500), response_content_type


async def handle_direct_request(path, method='GET', post_data=None, query_params=None, request_headers=None):
    """Обработка прямых URL запросов"""

    target_url = build_url([path], query_params)

    # Улучшенная проверка видео с использованием HEAD запроса
    is_video = False
    content_info = {}

    if method.upper() == 'GET':
        is_video, content_info = await is_video_content(target_url, request_headers)

    if is_video:
        logger.info(f"Video content detected, using streaming: {target_url}")
        range_header = request_headers.get(
            'Range') if request_headers else None
        return await stream_video_with_range(target_url, request_headers, range_header), 200, ''

    logger.info(f"Proxying {method} request to: {target_url}")
    response = await make_request(target_url, method, post_data, request_headers)

    # Если ответ StreamingResponse, возвращаем как есть
    if isinstance(response, StreamingResponse):
        return response, 200, ''

    content_type = response.get('headers', {}).get('content-type', '').lower()
    return response.get('body'), response.get('status', 500), content_type


async def handle_request(path, method='GET', post_data=None, query_params=None, request_headers=None):
    """Основной обработчик запросов"""
    segments = [s for s in path.strip('/').split('/') if s]
    logger.info(f"Handling {method} request: /{path}")

    if not segments:
        return {'error': 'Empty request path'}, 400, 'application/json'

    handler_type = segments[0]
    logger.info(f"Using handler: {handler_type}")

    try:
        if handler_type in ['enc', 'enc1', 'enc2', 'enc3']:
            response = await handle_encoded_request(
                segments,
                method,
                post_data,
                query_params,
                request_headers)

        else:
            response = await handle_direct_request(
                path,
                method,
                post_data,
                query_params,
                request_headers)

        return response

    except ValueError as e:
        logger.error(f"✕ Value error in request handling: {str(e)}")
        return {'error': str(e)}, 400, 'application/json'

    except httpx.TimeoutException as e:
        logger.error(f"✕ Timeout error in request handling: {str(e)}")
        return {'error': f'Request timeout: {str(e)}'}, 408, 'application/json'

    except HTTPException as e:
        # Пробрасываем HTTPException как есть
        raise e

    except Exception as e:
        logger.error(f"✕ Request handling error: {str(e)}")
        # Добавляем более детальную информацию об ошибке
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {'error': f'Internal server error: {str(e)}'}, 500, 'application/json'

# ==================== FastAPI Routes ====================


@app.get("/")
async def root():
    """Корневой эндпоинт с информацией о сервере"""
    return {
        "message": "Lampa Proxy Server with Enhanced Video Detection and Range Support is running",
        "status": "active",
        "version": "3.2.1",
        "timestamp": datetime.now().isoformat(),
        "supported_handlers": ["enc", "enc1", "enc2", "enc3"],
        "video_streaming": True,
        "range_support": True,
        "enhanced_video_detection": True,
        "proxy_enabled": CONFIG['use_proxy'],
        "total_proxies": len(CONFIG['proxy_list']),
        "working_proxies": len(proxy_manager.working_proxies),
        "config": {
            "proxy_enabled": CONFIG['use_proxy'],
            "total_proxies": len(CONFIG['proxy_list']),
            "working_proxies": len(proxy_manager.working_proxies),
            "max_redirects": CONFIG['max_redirects'],
            "timeout": CONFIG['timeout'],
            "max_proxy_retries": CONFIG['max_proxy_retries'],
            "stream_chunk_size": CONFIG['stream_chunk_size'],
            "stream_timeout": CONFIG['stream_timeout'],
            "max_range_size": CONFIG['max_range_size'],
            "stream_chunk_size": CONFIG['stream_chunk_size'],
            "head_request_timeout": CONFIG['head_request_timeout'],
            "timeouts": {
                "connect": CONFIG['timeout_connect'],
                "read": CONFIG['timeout_read'],
                "stream": CONFIG['stream_timeout'],
            }
        }
    }


@app.get("/health")
async def health_check():
    """Эндпоинт проверки здоровья"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "lampa-proxy-enhanced",
    }


@app.get("/status")
async def status_check():
    """Детальный статус сервера"""
    return {
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "config": {
            k: v for k, v in CONFIG.items()
            if not isinstance(v, (list, dict)) and not k.endswith('_timeout')
        }
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy(request: Request, path: str):
    """Основной FastAPI эндпоинт для всех прокси запросов"""

    # Пропускаем служебные эндпоинты
    if path in ["", "health", "status"]:
        return JSONResponse(
            content={
                'error': 'Use direct endpoints for server information'},
            status_code=400
        )

    # Быстрое извлечение заголовков
    request_headers = {}
    for header in ['User-Agent', 'Accept', 'Content-Type', 'Origin', 'Referer', 'Cookie', 'Range', 'Authorization']:
        if value := request.headers.get(header):
            request_headers[header] = value

    # Логируем Range заголовок для отладки перемотки
    if 'Range' in request_headers:
        logger.info(f"Client Range header: {request_headers['Range']}")

    post_data = None

    # Извлечение тела запроса
    if request.method in ["POST", "PUT", "DELETE"]:
        try:
            content_type = request.headers.get('content-type', '').lower()
            if 'application/x-www-form-urlencoded' in content_type:
                body = await request.body()
                post_data = body.decode('utf-8')

            elif 'multipart/form-data' in content_type:
                form_data = await request.form()
                post_data = dict(form_data)
                
            elif 'application/json' in content_type:
                post_data = await request.body()

            else:
                post_data = await request.body()

        except Exception as e:
            logger.error(f"Error reading request body: {e}")
            return JSONResponse(
                content={'error': f'Failed to read request body: {str(e)}'},
                status_code=400
            )

    # Извлечение параметров запроса
    query_params = dict(request.query_params)

    try:
        response_body, response_status, response_content_type = await handle_request(
            path,
            request.method,
            post_data,
            query_params,
            request_headers)

        # Если результат StreamingResponse (для видео), возвращаем как есть
        if isinstance(response_body, StreamingResponse):
            return response_body

        # Обработка ошибок
        if isinstance(response_body, dict) and 'error' in response_body:
            return JSONResponse(
                content=response_body,
                status_code=response_status,
                headers={'Access-Control-Allow-Origin': '*'}
            )

        if 'application/json' in response_content_type:
            # Если response_body уже словарь, используем как есть
            if isinstance(response_body, dict):
                content = response_body
            else:
                # Иначе пытаемся распарсить JSON
                try:
                    content = json.loads(
                        response_body) if response_body else {}

                except:
                    content = response_body

            return JSONResponse(
                content=content,
                status_code=response_status,
                headers={'Access-Control-Allow-Origin': '*'}
            )

        return Response(
            content=response_body if isinstance(
                response_body, bytes) else str(response_body).encode(),
            status_code=response_status,
            media_type=response_content_type,
            headers={
                'Access-Control-Allow-Origin': '*',
                'Content-Type': response_content_type,
            }
        )

    except HTTPException as e:
        # Обрабатываем HTTPException отдельно
        return JSONResponse(
            status_code=e.status_code,
            content={'error': e.detail},
            headers={'Access-Control-Allow-Origin': '*'}
        )

    except asyncio.CancelledError:
        logger.info("Request was cancelled by client")
        return Response(status_code=499)

    except Exception as e:
        logger.error(f"Proxy handler error: {e}")
        return JSONResponse(
            status_code=500,
            content={'error': f'Internal server error: {str(e)}'},
            headers={'Access-Control-Allow-Origin': '*'}
        )


@app.options("/{path:path}")
async def options_handler():
    """Обработчик OPTIONS запросов для CORS"""
    return Response(headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': '*',
        'Access-Control-Allow-Headers': '*'
    })

# ==================== ЗАПУСК СЕРВЕРА ====================

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv('PORT', '8080')),
        access_log=False,
        loop="asyncio",
        limit_max_requests=1000,  # Автоматически перезапускаться после 1000 запросов
        timeout_notify=30,
        timeout_keep_alive=5
    )
