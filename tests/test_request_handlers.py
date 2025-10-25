#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from src.proxy_server import (
    handle_encoded_request,
    handle_direct_request,
    handle_request,
    handle_redirect
)
import pytest
import base64
from unittest.mock import patch, AsyncMock, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestRequestHandlers:
    """Тесты обработчиков запросов"""

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc(self):
        """Тест обработки enc запроса"""
        # Создаем правильные тестовые данные
        test_data = "param/User-Agent=TestAgent/https://example.com/api"
        encoded_data = base64.b64encode(
            test_data.encode()).decode().rstrip('=')
        segments = ["enc", encoded_data, "additional", "segments"]

        with patch('src.proxy_server.make_request') as mock_request:
            mock_request.return_value = {
                'body': '{"result": "success"}',
                'status': 200,
                'headers': {'content-type': 'application/json'}
            }

            with patch('src.proxy_server.is_video_content') as mock_video:
                mock_video.return_value = (False, {})

                response, status, content_type = await handle_encoded_request(
                    segments, 'GET', None, {}, {}
                )

                assert status == 200
                mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc2(self):
        """Тест обработки enc2 запроса"""
        test_url = "https://example.com/api"
        encoded_data = base64.b64encode(test_url.encode()).decode().rstrip('=')
        segments = ["enc2", encoded_data]

        with patch('src.proxy_server.make_request') as mock_request:
            mock_request.return_value = {
                'body': 'response data',
                'status': 200,
                'headers': {'content-type': 'text/plain'}
            }

            with patch('src.proxy_server.is_video_content') as mock_video:
                mock_video.return_value = (False, {})

                response, status, content_type = await handle_encoded_request(
                    segments, 'GET', None, {}, {}
                )

                assert status == 200

    @pytest.mark.asyncio
    async def test_handle_encoded_request_video(self):
        """Тест обработки видео запроса через enc"""
        # Создаем правильные тестовые данные с видео URL
        test_data = "param/User-Agent=TestAgent/https://example.com/video.mp4"
        encoded_data = base64.b64encode(
            test_data.encode()).decode().rstrip('=')
        segments = ["enc", encoded_data, "video.mp4"]

        with patch('src.proxy_server.is_video_content') as mock_video:
            mock_video.return_value = (True, {})

            with patch('src.proxy_server.stream_video_with_range') as mock_stream:
                mock_stream.return_value = "streaming_response"

                response, status, content_type = await handle_encoded_request(
                    segments, 'GET', None, {}, {}
                )

                assert response == "streaming_response"
                mock_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_direct_request(self):
        """Тест обработки прямого запроса"""
        test_url = "https://example.com/api"

        with patch('src.proxy_server.make_request') as mock_request:
            mock_request.return_value = {
                'body': 'response data',
                'status': 200,
                'headers': {'content-type': 'text/plain'}
            }

            with patch('src.proxy_server.is_video_content') as mock_video:
                mock_video.return_value = (False, {})

                response, status, content_type = await handle_direct_request(
                    test_url, 'GET', None, {}, {}
                )

                assert status == 200
                assert response == 'response data'

    @pytest.mark.asyncio
    async def test_handle_direct_request_video(self):
        """Тест обработки прямого видео запроса"""
        test_url = "https://example.com/video.mp4"

        with patch('src.proxy_server.is_video_content') as mock_video:
            mock_video.return_value = (True, {})

            with patch('src.proxy_server.stream_video_with_range') as mock_stream:
                mock_stream.return_value = "streaming_response"

                response, status, content_type = await handle_direct_request(
                    test_url, 'GET', None, {}, {'Range': 'bytes=0-999'}
                )

                assert response == "streaming_response"

    @pytest.mark.asyncio
    async def test_handle_request_encoded(self):
        """Тест основного обработчика для encoded запросов"""
        test_data = "param/User-Agent=TestAgent/https://example.com/api"
        encoded_data = base64.b64encode(
            test_data.encode()).decode().rstrip('=')
        path = f"enc/{encoded_data}"

        with patch('src.proxy_server.handle_encoded_request') as mock_handler:
            mock_handler.return_value = ('response', 200, 'application/json')

            response, status, content_type = await handle_request(
                path, 'GET', None, {}, {}
            )

            assert status == 200
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_request_direct(self):
        """Тест основного обработчика для прямых запросов"""
        path = "https://example.com/api"

        with patch('src.proxy_server.handle_direct_request') as mock_handler:
            mock_handler.return_value = ('response', 200, 'application/json')

            response, status, content_type = await handle_request(
                path, 'GET', None, {}, {}
            )

            assert status == 200
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_request_error(self):
        """Тест обработки ошибок в основном обработчике"""
        path = "invalid/path"

        with patch('src.proxy_server.handle_direct_request') as mock_handler:
            mock_handler.side_effect = ValueError("Test error")

            response, status, content_type = await handle_request(
                path, 'GET', None, {}, {}
            )

            assert status == 400
            assert 'error' in response

    @pytest.mark.asyncio
    async def test_handle_request_timeout(self):
        """Тест обработки таймаута в основном обработчике"""
        path = "https://example.com/api"

        with patch('src.proxy_server.handle_direct_request') as mock_handler:
            mock_handler.side_effect = Exception("Timeout error")

            response, status, content_type = await handle_request(
                path, 'GET', None, {}, {}
            )

            assert status == 500
            assert 'error' in response


class TestRedirectHandling:
    """Тесты обработки редиректов"""

    @pytest.mark.asyncio
    async def test_handle_redirect(self):
        """Тест обработки HTTP редиректа"""
        mock_response = AsyncMock()
        mock_response.headers = {'location': 'https://redirected.example.com'}
        mock_response.url = 'https://original.example.com'

        with patch('src.proxy_server.make_request') as mock_make_request:
            mock_make_request.return_value = {
                'body': 'redirected response',
                'status': 200,
                'headers': {}
            }

            result = await handle_redirect(
                mock_response, {}, 'GET', None, 0
            )

            assert result['body'] == 'redirected response'
            mock_make_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_redirect_too_many(self):
        """Тест обработки слишком большого количества редиректов"""
        mock_response = AsyncMock()
        mock_response.headers = {'location': 'https://redirected.example.com'}

        with pytest.raises(ValueError, match="Too many redirects"):
            await handle_redirect(
                mock_response, {}, 'GET', None, 10  # Превышаем максимальное количество
            )

    @pytest.mark.asyncio
    async def test_handle_redirect_no_location(self):
        """Тест обработки редиректа без Location заголовка"""
        mock_response = AsyncMock()
        mock_response.headers = {}  # Нет location

        with pytest.raises(ValueError, match="Redirect response without Location header"):
            await handle_redirect(
                mock_response, {}, 'GET', None, 0
            )

    @pytest.mark.asyncio
    async def test_handle_redirect_relative_url(self):
        """Тест обработки относительного URL в редиректе"""
        mock_response = AsyncMock()
        mock_response.headers = {'location': '/new-path'}
        mock_response.url = 'https://original.example.com/api'

        with patch('src.proxy_server.make_request') as mock_make_request:
            mock_make_request.return_value = {
                'body': 'redirected response',
                'status': 200,
                'headers': {}
            }

            await handle_redirect(
                mock_response, {}, 'GET', None, 0
            )

            # Проверяем что относительный URL был преобразован в абсолютный
            expected_url = 'https://original.example.com/new-path'
            mock_make_request.assert_called_once()
