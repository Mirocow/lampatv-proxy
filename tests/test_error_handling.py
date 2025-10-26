#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import HTTPException
from src.proxy_server import (
    make_direct_request,
    make_request_with_proxy,
    handle_direct_request,
    handle_request
)
import base64
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestErrorHandling:
    """Тесты обработки ошибок"""

    @pytest.mark.asyncio
    async def test_make_direct_request_timeout(self):
        """Тест таймаута прямого запроса"""
        with patch('src.proxy_server.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request.side_effect = Exception(
                "Timeout")

            result = await make_direct_request("https://example.com")
            assert result['status'] == 500
            assert 'error' in result

    @pytest.mark.asyncio
    async def test_make_direct_request_connection_error(self):
        """Тест ошибки соединения в прямом запросе"""
        with patch('src.proxy_server.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.request.side_effect = Exception(
                "Connection failed")

            result = await make_direct_request("https://example.com")
            assert result['status'] == 500
            assert 'error' in result

    @pytest.mark.asyncio
    async def test_make_request_with_proxy_all_failures(self):
        """Тест когда все прокси не работают"""
        with patch('src.proxy_server.proxy_manager') as mock_manager:
            mock_manager.get_random_proxy.return_value = "http://proxy:8080"
            mock_manager.working_proxies = ["http://proxy:8080"]

            with patch('src.proxy_server.make_direct_request') as mock_direct:
                mock_direct.side_effect = Exception("All proxies failed")

                result = await make_request_with_proxy("https://example.com")
                assert result['status'] == 404  # Fallback to direct request

    @pytest.mark.asyncio
    async def test_handle_direct_request_video_stream_error(self):
        """Тест ошибки при потоковой передаче видео"""
        with patch('src.proxy_server.is_video_content') as mock_video:
            mock_video.return_value = (True, {})

            with patch('src.proxy_server.stream_video_with_range') as mock_stream:
                mock_stream.side_effect = HTTPException(
                    status_code=500, detail="Stream error")

                with pytest.raises(HTTPException):
                    await handle_direct_request(
                        "https://example.com/video.mp4",
                        'GET', None, {}, {'Range': 'bytes=0-999'}
                    )

    @pytest.mark.asyncio
    async def test_handle_request_empty_path(self):
        """Тест обработки пустого пути"""
        result = await handle_request("", 'GET', None, {}, {})
        assert 'error' in result[0]
        assert result[1] == 400

    @pytest.mark.asyncio
    async def test_handle_request_unknown_handler(self):
        """Тест обработки неизвестного обработчика"""
        # Простой URL без специального обработчика
        result = await handle_request("https://google.com", 'GET', None, {}, {})
        # Должен использовать handle_direct_request
        assert result[1] == 200  # Mock возвращает 200

    @pytest.mark.asyncio
    async def test_handle_request_unexpected_error(self):
        """Тест обработки непредвиденной ошибки"""
        with patch('src.proxy_server.handle_direct_request') as mock_handler:
            mock_handler.side_effect = Exception("Unexpected error")

            result = await handle_request("https://example.com", 'GET', None, {}, {})
            assert result[1] == 500
            assert 'error' in result[0]
