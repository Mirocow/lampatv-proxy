#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi.responses import StreamingResponse
from fastapi import HTTPException
from src.proxy_server import (
    decode_base64_url,
    normalize_url,
    parse_encoded_data,
    build_url,
    is_video_url,
    parse_range_header,
    is_valid_json,
    parse_cookie_plus_params,
    handle_redirect,
    make_direct_request,
    make_request_with_proxy,
    get_content_info,
    is_video_content,
    stream_video_with_range
)
import pytest
import asyncio
import json
import base64
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestProxyServerComprehensive:
    """Комплексные тесты для полного покрытия proxy_server.py"""

    def test_decode_base64_url_with_special_chars(self):
        """Тест декодирования base64 URL со специальными символами"""
        test_url = "https://example.com/path?param=value&other=test"
        encoded = base64.b64encode(test_url.encode()).decode().rstrip('=')

        decoded = decode_base64_url(encoded)
        assert decoded == test_url

    def test_normalize_url_complex_cases(self):
        """Тест нормализации сложных URL случаев"""
        test_cases = [
            ("https://https://example.com", "https://example.com"),
            ("http://https://example.com", "https://example.com"),
            ("//example.com", "https://example.com"),
            ("example.com/path?query=1", "https://example.com/path?query=1"),
        ]

        for input_url, expected in test_cases:
            result = normalize_url(input_url)
            assert result == expected

    def test_parse_encoded_data_complex(self):
        """Тест парсинга сложных закодированных данных"""
        # Тест с несколькими параметрами и URL
        test_data = "param/User-Agent=TestAgent/param/Referer=https://site.com/param/Accept=application/json/https://example.com/api/v1"

        params, segments = parse_encoded_data(test_data)
        assert params["User-Agent"] == "TestAgent"
        assert params["Referer"] == "https://site.com"
        assert params["Accept"] == "application/json"
        assert "https://example.com/api/v1" in segments

    def test_parse_encoded_data_no_url(self):
        """Тест парсинга данных без URL"""
        test_data = "param/key1=value1/param/key2=value2"

        params, segments = parse_encoded_data(test_data)
        assert params["key1"] == "value1"
        assert params["key2"] == "value2"
        assert segments == []

    def test_build_url_complex(self):
        """Тест построения сложных URL"""
        # URL с уже существующими query параметрами
        segments = ["https://example.com/api?existing=1"]
        query_params = {"new": "value", "another": "test"}

        result = build_url(segments, query_params)
        assert "existing=1" in result
        assert "new=value" in result
        assert "another=test" in result

    def test_is_video_url_edge_cases(self):
        """Тест определения видео URL для граничных случаев"""
        video_cases = [
            "https://example.com/video.m3u8?token=abc",
            "https://example.com/stream/manifest.mpd",
            "https://example.com/hls/playlist.m3u8",
            "https://cdn.example.com/video/12345.mp4",
        ]

        non_video_cases = [
            "https://example.com/video.jpg",
            "https://example.com/stream.json",
            "https://example.com/playlist.txt",
        ]

        for url in video_cases:
            assert is_video_url(url) is True

        for url in non_video_cases:
            assert is_video_url(url) is False

    def test_parse_range_header_edge_cases(self):
        """Тест парсинга Range заголовка для граничных случаев"""
        test_cases = [
            ("bytes=0-", 1000, (0, 999)),
            ("bytes=-100", 1000, (900, 999)),
            ("bytes=100-", 50, (100, 49)),  # start > file_size
            ("bytes=1000-2000", 500, (1000, 499)),  # start > file_size
            ("bytes=300-200", 1000, (200, 300)),  # start > end
        ]

        for range_header, file_size, expected in test_cases:
            result = parse_range_header(range_header, file_size)
            assert result == expected

    def test_is_valid_json_edge_cases(self):
        """Тест проверки JSON для граничных случаев"""
        valid_cases = [
            '123',
            '3.14',
            '"string"',
            'true',
            'false',
            'null',
            '[]',
            '{}'
        ]

        invalid_cases = [
            'undefined',
            '{key: "value"}',
            "[1, 2, 3",
            '{"key": "value"',
            '',
            '   ',
            None
        ]

        for json_str in valid_cases:
            assert is_valid_json(json_str) is True

        for json_str in invalid_cases:
            if json_str is not None:
                assert is_valid_json(json_str) is False

    def test_parse_cookie_plus_params_edge_cases(self):
        """Тест парсинга cookie и параметров для граничных случаев"""
        # Тест без параметров
        segments = ["enc", "https://example.com"]
        params = parse_cookie_plus_params(segments)
        assert params == {}

        # Тест с разными типами параметров
        segments = [
            "enc", "param", "Cookie=session=abc123", "param",
            "Authorization=Bearer token", "param", "Custom-Header=value",
            "https://example.com"
        ]

        params = parse_cookie_plus_params(segments)
        assert params["Cookie"] == "session=abc123"
        assert params["Authorization"] == "Bearer token"
        assert params["Custom-Header"] == "value"

    @pytest.mark.asyncio
    async def test_handle_redirect_complex(self):
        """Тест обработки сложных редиректов"""
        mock_response = AsyncMock()
        mock_response.headers = {'location': 'https://redirected.com/new-path'}
        mock_response.url = 'https://original.com'

        with patch('src.proxy_server.make_request') as mock_make_request:
            mock_make_request.return_value = {
                'body': 'redirected content',
                'status': 200,
                'headers': {}
            }

            result = await handle_redirect(
                mock_response,
                {'User-Agent': 'test'},
                'GET',
                None,
                2
            )

            assert result['body'] == 'redirected content'
            mock_make_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_redirect_max_redirects(self):
        """Тест обработки превышения максимального количества редиректов"""
        mock_response = AsyncMock()
        mock_response.headers = {'location': 'https://redirected.com'}

        with pytest.raises(ValueError, match="Too many redirects"):
            await handle_redirect(mock_response, {}, 'GET', None, 10)

    @pytest.mark.asyncio
    async def test_handle_redirect_no_location(self):
        """Тест редиректа без Location заголовка"""
        mock_response = AsyncMock()
        mock_response.headers = {}

        with pytest.raises(ValueError, match="Redirect response without Location header"):
            await handle_redirect(mock_response, {}, 'GET', None, 0)

    @pytest.mark.asyncio
    async def test_make_direct_request_complex(self):
        """Тест сложных случаев прямого запроса"""
        # Тест с редиректом
        mock_response = AsyncMock()
        mock_response.status_code = 302
        mock_response.headers = {'location': 'https://redirected.com'}
        mock_response.url = 'https://original.com'

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.request.return_value = mock_response

        with patch('src.proxy_server.httpx.AsyncClient', return_value=mock_client):
            with patch('src.proxy_server.handle_redirect') as mock_redirect:
                mock_redirect.return_value = {
                    'body': 'redirected',
                    'status': 200,
                    'headers': {}
                }

                result = await make_direct_request("https://example.com")
                assert result['body'] == 'redirected'

    @pytest.mark.asyncio
    async def test_make_direct_request_with_post_data(self):
        """Тест прямого запроса с POST данными"""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.text = '{"result": "success"}'
        mock_response.url = 'https://example.com/api'

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.request.return_value = mock_response

        with patch('src.proxy_server.httpx.AsyncClient', return_value=mock_client):
            result = await make_direct_request(
                "https://example.com/api",
                "POST",
                {"key": "value"}
            )
            assert result['status'] == 200

    @pytest.mark.asyncio
    async def test_make_request_with_proxy_no_working_proxies(self):
        """Тест запроса через прокси когда нет рабочих прокси"""
        with patch('src.proxy_server.proxy_manager') as mock_manager:
            mock_manager.working_proxies = []
            mock_manager.get_random_proxy.return_value = None

            with patch('src.proxy_server.make_direct_request') as mock_direct:
                mock_direct.return_value = {'status': 200, 'body': 'success'}

                result = await make_request_with_proxy("https://example.com")
                assert result['status'] == 200
                mock_direct.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_content_info_error_handling(self):
        """Тест обработки ошибок в get_content_info"""
        with patch('src.proxy_server.httpx.AsyncClient') as mock_client:
            mock_client.side_effect = Exception("Connection failed")

            content_info = await get_content_info("https://example.com", {})
            assert content_info['status_code'] == 0
            assert 'error' in content_info

    @pytest.mark.asyncio
    async def test_is_video_content_error_fallback(self):
        """Тест fallback при ошибке определения видео контента"""
        with patch('src.proxy_server.get_content_info') as mock_info:
            mock_info.side_effect = Exception("Test error")

            # Для видео URL должен вернуть True при ошибке
            is_video, content_info = await is_video_content("https://example.com/video.mp4")
            assert is_video is True
            assert content_info == {}

            # Для не-видео URL должен вернуть False при ошибке
            is_video, content_info = await is_video_content("https://example.com/data.json")
            assert is_video is False

    @pytest.mark.asyncio
    async def test_stream_video_with_range_error_handling(self):
        """Тест обработки ошибок в потоковой передаче видео"""
        with patch('src.proxy_server.get_content_info') as mock_info:
            mock_info.side_effect = Exception("Content info error")

            with pytest.raises(HTTPException):
                await stream_video_with_range(
                    "https://example.com/video.mp4",
                    {},
                    "bytes=0-999"
                )

    @pytest.mark.asyncio
    async def test_stream_video_unknown_file_size(self):
        """Тест потоковой передачи видео с неизвестным размером файла"""
        with patch('src.proxy_server.get_content_info') as mock_info:
            mock_info.return_value = {
                'status_code': 200,
                'content_type': 'video/mp4',
                'content_length': 0,  # Неизвестный размер
                'accept_ranges': 'bytes'
            }

            with patch('src.proxy_server.StreamingResponse') as mock_stream:
                mock_stream.return_value = MagicMock()

                response = await stream_video_with_range(
                    "https://example.com/video.mp4",
                    {"Range": "bytes=0-999"}
                )

                assert response is not None
