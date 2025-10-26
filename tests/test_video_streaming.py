#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from src.proxy_server import stream_video_with_range, parse_range_header, is_video_url
import pytest
import httpx
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


class TestVideoStreaming:
    """Тесты для исправлений потокового видео"""

    @pytest.mark.asyncio
    async def test_stream_video_with_seeking(self):
        """Тест потоковой передачи с перемоткой"""
        with patch('src.proxy_server.get_content_info') as mock_content_info, \
                patch('src.proxy_server.httpx.AsyncClient') as mock_client:

            # Настраиваем моки
            mock_content_info.return_value = {
                'status_code': 200,
                'content_type': 'video/mp4',
                'content_length': 10000000,
                'accept_ranges': 'bytes'
            }

            # Мок ответа от сервера
            mock_response = AsyncMock()
            mock_response.status_code = 206
            mock_response.headers = {
                'content-type': 'video/mp4',
                'content-range': 'bytes 1000-1999/10000000',
                'content-length': '1000'
            }
            mock_response.aiter_bytes.return_value = [b'test_chunk']

            mock_client_instance = AsyncMock()
            mock_client_instance.stream.return_value.__aenter__.return_value = mock_response
            mock_client.return_value = mock_client_instance

            # Тестируем перемотку
            target_url = 'https://example.com/video.mp4'
            request_headers = {'Range': 'bytes=1000-1999'}

            response = await stream_video_with_range(target_url, request_headers, 'bytes=1000-1999')

            # Проверяем, что ответ корректный
            assert response.status_code == 206
            assert 'Content-Range' in response.headers

    @pytest.mark.asyncio
    async def test_stream_video_unknown_size(self):
        """Тест потоковой передачи с неизвестным размером"""
        with patch('src.proxy_server.get_content_info') as mock_content_info, \
                patch('src.proxy_server.httpx.AsyncClient') as mock_client:

            # Неизвестный размер файла
            mock_content_info.return_value = {
                'status_code': 200,
                'content_type': 'video/mp4',
                'content_length': 0,
                'accept_ranges': 'bytes'
            }

            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {'content-type': 'video/mp4'}
            mock_response.aiter_bytes.return_value = [
                b'chunk1', b'chunk2', b'']

            mock_client_instance = AsyncMock()
            mock_client_instance.stream.return_value.__aenter__.return_value = mock_response
            mock_client.return_value = mock_client_instance

            target_url = 'https://example.com/live_stream.m3u8'
            request_headers = {'Range': 'bytes=500-'}

            response = await stream_video_with_range(target_url, request_headers, 'bytes=500-')

            # Должен вернуть 206 даже при неизвестном размере
            assert response.status_code == 206

    def test_parse_range_header_complex_cases(self):
        """Тест парсинга сложных Range заголовков"""
        test_cases = [
            # (range_header, file_size, expected_start, expected_end)
            ("bytes=100-199", 1000, (100, 199)),
            ("bytes=500-", 1000, (500, 999)),
            ("bytes=500-", 0, (500, 500 + 50*1024*1024 - 1)),  # unknown size
            ("bytes=-500", 1000, (500, 999)),  # suffix
            ("bytes=1500-2000", 1000, (999, 999)),  # out of bounds
            (None, 1000, (0, 999)),
            ("invalid", 1000, (0, 999)),
        ]

        for range_header, file_size, expected in test_cases:
            start, end = parse_range_header(range_header, file_size)
            assert (start, end) == expected, f"Failed for {range_header}"


    def test_video_url_detection_comprehensive(self):
        """Комплексный тест определения видео URL"""

        # Позитивные случаи - должны определяться как видео
        video_urls = [
            # Стандартные видеофайлы
            "https://example.com/video.mp4",
            "https://example.com/path/to/video.mkv?token=abc&time=123",
            "https://cdn.com/movie.avi#fragment",

            # HLS потоки
            "https://stream.com/playlist.m3u8",
            "https://example.com/hls/index.m3u8",
            "https://cdn.com/live/stream.m3u8?quality=hd",
            "https://example.com/adaptive/hls.m3u8",

            # DASH потоки
            "https://example.com/manifest.mpd",
            "https://cdn.com/stream/manifest.mpd?start=100",

            # Пути с видео-индикаторами
            "https://example.com/video/stream123",
            "https://cdn.com/stream/live-event",
            "https://api.com/hls/broadcast",
            "https://video.com/dash/playlist",

            # TS сегменты
            "https://example.com/segment1.ts",
            "https://cdn.com/chunks/segment_500.ts?offset=1000",

            # Разные видео форматы
            "https://example.com/film.mov",
            "https://cdn.com/clip.wmv",
            "https://video.com/short.webm",
        ]

        # Негативные случаи - НЕ должны определяться как видео
        non_video_urls = [
            "https://example.com/image.jpg",
            "https://cdn.com/document.pdf",
            "https://site.com/audio.mp3",
            "https://api.com/data.json",
            "https://example.com/page.html",
            "https://cdn.com/archive.zip",
            "https://site.com/script.js",
            "https://example.com/styles.css",
        ]

        # Проверяем позитивные случаи
        for url in video_urls:
            assert is_video_url(url), f"Should detect as video: {url}"

        # Проверяем негативные случаи
        for url in non_video_urls:
            assert not is_video_url(url), f"Should NOT detect as video: {url}"


        @pytest.mark.asyncio
        async def test_stream_resume_after_seek(self):
            """Тест возобновления потока после перемотки"""
            with patch('src.proxy_server.get_content_info') as mock_content_info, \
                    patch('src.proxy_server.httpx.AsyncClient') as mock_client:

                mock_content_info.return_value = {
                    'status_code': 200,
                    'content_type': 'video/mp4',
                    'content_length': 5000000,
                    'accept_ranges': 'bytes'
                }

                # Имитируем несколько чанков
                mock_response = AsyncMock()
                mock_response.status_code = 206
                mock_response.headers = {
                    'content-type': 'video/mp4',
                    'content-range': 'bytes 1000-5999/5000000',
                    'content-length': '5000'
                }
                # Возвращаем несколько чанков
                mock_response.aiter_bytes.return_value = [
                    b'chunk1' * 100,
                    b'chunk2' * 100,
                    b'chunk3' * 100
                ]

                mock_client_instance = AsyncMock()
                mock_client_instance.stream.return_value.__aenter__.return_value = mock_response
                mock_client.return_value = mock_client_instance

                # Запрос с середины видео
                target_url = 'https://example.com/movie.mp4'
                request_headers = {'Range': 'bytes=1000-5999'}

                response = await stream_video_with_range(target_url, request_headers, 'bytes=1000-5999')

                # Проверяем корректность ответа
                assert response.status_code == 206
                assert '5000' in response.headers.get('Content-Length', '')

    @pytest.mark.asyncio
    async def test_stream_live_video(self):
        """Тест потоковой передачи live видео (без известного размера)"""
        with patch('src.proxy_server.get_content_info') as mock_content_info, \
                patch('src.proxy_server.httpx.AsyncClient') as mock_client:

            # Live поток без известного размера
            mock_content_info.return_value = {
                'status_code': 200,
                'content_type': 'application/x-mpegurl',
                'content_length': 0,
                'accept_ranges': 'bytes'
            }

            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {'content-type': 'application/x-mpegurl'}
            # Бесконечный поток чанков

            async def chunk_generator():
                chunk_count = 0
                while chunk_count < 10:  # Ограничиваем для теста
                    yield f"chunk_{chunk_count}".encode()
                    chunk_count += 1
                    await asyncio.sleep(0.01)

            mock_response.aiter_bytes.return_value = chunk_generator()

            mock_client_instance = AsyncMock()
            mock_client_instance.stream.return_value.__aenter__.return_value = mock_response
            mock_client.return_value = mock_client_instance

            target_url = 'https://live.example.com/stream.m3u8'

            response = await stream_video_with_range(target_url, {}, None)

            # Должен вернуть 200 для live потоков
            assert response.status_code == 200


