#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import httpx
from fastapi.testclient import TestClient

from .main import app, is_video_url, normalize_url, decode_base64_url

client = TestClient(app)


class TestVideoDetection:
    """Тесты для улучшенной системы обнаружения видео"""

    @pytest.mark.asyncio
    async def test_is_video_url_positive(self):
        """Тест положительного определения видео по URL"""
        video_urls = [
            "https://example.com/video.mp4",
            "http://test.com/movie.mkv",
            "https://stream.com/playlist.m3u8",
            "https://cdn.com/manifest.mpd",
            "https://example.com/hls/index.m3u8"
        ]

        for url in video_urls:
            assert is_video_url(url), f"Should detect video URL: {url}"

    @pytest.mark.asyncio
    async def test_is_video_url_negative(self):
        """Тест отрицательного определения видео по URL"""
        non_video_urls = [
            "https://example.com/image.jpg",
            "http://test.com/document.pdf",
            "https://api.com/data.json",
            "https://website.com/index.html"
        ]

        for url in non_video_urls:
            assert not is_video_url(
                url), f"Should not detect as video URL: {url}"

    @pytest.mark.asyncio
    async def test_video_detection_with_head_request(self):
        """Тест обнаружения видео через HEAD запрос"""
        from .main import is_video_content

        # Мокаем успешный HEAD запрос с видео content-type
        with patch('httpx.AsyncClient.head') as mock_head:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {
                'content-type': 'video/mp4',
                'content-length': '1000000',
                'accept-ranges': 'bytes'
            }
            mock_head.return_value.__aenter__.return_value = mock_response

            is_video, info = await is_video_content(
                "https://example.com/video.mp4",
                {"User-Agent": "test"}
            )

            assert is_video == True
            assert info['content_type'] == 'video/mp4'

    @pytest.mark.asyncio
    async def test_video_detection_fallback_to_get(self):
        """Тест fallback на GET при неудачном HEAD запросе"""
        from .main import is_video_content

        # Мокаем неудачный HEAD запрос и успешный GET
        with patch('httpx.AsyncClient.head', side_effect=Exception("HEAD failed")):
            with patch('httpx.AsyncClient.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 206
                mock_response.headers = {
                    'content-type': 'video/mp4',
                    'content-range': 'bytes 0-1/1000000'
                }
                mock_get.return_value.__aenter__.return_value = mock_response

                is_video, info = await is_video_content(
                    "https://example.com/video.mp4",
                    {"User-Agent": "test"}
                )

                assert is_video == True


class TestURLProcessing:
    """Тесты обработки URL"""

    def test_normalize_url(self):
        """Тест нормализации URL"""
        test_cases = [
            ("example.com/video", "https://example.com/video"),
            ("http://example.com", "http://example.com"),
            ("https://https://example.com", "https://example.com"),
            ("http://http://example.com", "http://example.com")
        ]

        for input_url, expected in test_cases:
            result = normalize_url(input_url)
            assert result == expected, f"Normalization failed for {input_url}"

    def test_decode_base64_url(self):
        """Тест декодирования base64 URL"""
        test_string = "Hello World"
        encoded = base64.b64encode(test_string.encode()).decode()

        decoded = decode_base64_url(encoded)
        assert decoded == test_string


class TestAPIEndpoints:
    """Тесты API эндпоинтов"""

    def test_root_endpoint(self):
        """Тест корневого эндпоинта"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "status" in data

    def test_health_endpoint(self):
        """Тест эндпоинта здоровья"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_status_endpoint(self):
        """Тест эндпоинта статуса"""
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"


class TestStreamingFunctionality:
    """Тесты функциональности потоковой передачи"""

    @pytest.mark.asyncio
    async def test_range_header_parsing(self):
        """Тест парсинга заголовка Range"""
        from .main import parse_range_header

        test_cases = [
            ("bytes=0-499", 1000, (0, 499)),
            ("bytes=500-999", 1000, (500, 999)),
            ("bytes=500-", 1000, (500, 999)),
            ("bytes=-500", 1000, (500, 999)),
            (None, 1000, (0, 999))
        ]

        for range_header, file_size, expected in test_cases:
            result = parse_range_header(range_header, file_size)
            assert result == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
