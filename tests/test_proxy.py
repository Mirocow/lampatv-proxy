#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from proxy_server import app, decode_base64_url, normalize_url, parse_encoded_data, build_url, parse_cookie_header, is_valid_json, wrap_jsonp, ProxyManager, handle_encoded_request, handle_direct_request, handle_request
import pytest
import asyncio
import base64
import urllib.parse
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


client = TestClient(app)


class TestUtilityFunctions:
    """Тесты для вспомогательных функций"""

    def test_decode_base64_url(self):
        """Тест декодирования base64 URL"""
        test_string = "Hello, World! Тест"
        encoded = base64.b64encode(test_string.encode()).decode()
        encoded_url = urllib.parse.quote(encoded)

        result = decode_base64_url(encoded_url)
        assert result == test_string

    def test_decode_base64_url_with_padding(self):
        """Тест декодирования base64 с добавлением padding"""
        test_string = "test"
        encoded = base64.b64encode(test_string.encode()).decode().rstrip('=')
        encoded_url = urllib.parse.quote(encoded)

        result = decode_base64_url(encoded_url)
        assert result == test_string

    def test_normalize_url(self):
        """Тест нормализации URL"""
        assert normalize_url("example.com") == "https://example.com"
        assert normalize_url("http://example.com") == "http://example.com"
        assert normalize_url("https://example.com") == "https://example.com"
        assert normalize_url("https:/example.com") == "https://example.com"
        assert normalize_url(
            "https://http://example.com") == "https://example.com"

    def test_parse_encoded_data(self):
        """Тест парсинга закодированных данных"""
        # Тест с параметрами и URL
        encoded_data = "param/key1=value1/param/key2=value2/https://example.com/api"
        params, url_segments = parse_encoded_data(encoded_data)

        assert params == {'key1': 'value1', 'key2': 'value2'}
        assert url_segments == ['https://example.com/api']

        # Тест только с параметрами
        encoded_data2 = "param/key1=value1/param/key2=value2/"
        params2, url_segments2 = parse_encoded_data(encoded_data2)

        assert params2 == {'key1': 'value1', 'key2': 'value2'}
        assert url_segments2 == []

        # Тест только с URL
        encoded_data3 = "https://example.com/api/data"
        params3, url_segments3 = parse_encoded_data(encoded_data3)

        assert params3 == {}
        assert url_segments3 == ['https://example.com/api/data']

    def test_build_url(self):
        """Тест построения URL из сегментов"""
        segments = ['https://example.com', 'api', 'v1', 'data']
        url = build_url(segments)
        assert url == 'https://example.com/api/v1/data'

        segments2 = ['example.com', 'path']
        url2 = build_url(segments2)
        assert url2 == 'https://example.com/path'

    def test_parse_cookie_header(self):
        """Тест парсинга заголовков cookie"""
        cookie_header = "session=abc123; expires=Thu, 01 Jan 2020 00:00:00 GMT; path=/"
        cookies = parse_cookie_header(cookie_header)

        assert len(cookies) == 1
        assert cookies[0] == "session=abc123; expires=Thu, 01 Jan 2020 00:00:00 GMT; path=/"

        multiple_cookies = "session=abc123; user=john"
        cookies2 = parse_cookie_header(multiple_cookies)
        assert len(cookies2) == 2

    def test_is_valid_json(self):
        """Тест проверки валидности JSON"""
        assert is_valid_json('{"key": "value"}') == True
        assert is_valid_json('[1, 2, 3]') == True
        assert is_valid_json('invalid') == False
        assert is_valid_json('') == False
        assert is_valid_json('{invalid}') == False

    def test_wrap_jsonp(self):
        """Тест обертки JSONP"""
        callback = "myCallback"
        data = '{"test": "data"}'

        result = wrap_jsonp(callback, data)
        expected = 'myCallback("{\\"test\\": \\"data\\"}")'
        assert result == expected

        data_obj = {"key": "value"}
        result2 = wrap_jsonp(callback, data_obj)
        assert 'myCallback(' in result2
        assert '"key": "value"' in result2

    def test_wrap_jsonp_error_handling(self):
        """Тест обработки ошибок в JSONP обертке"""
        callback = "cb"
        result = wrap_jsonp(callback, object())
        assert 'cb({"error": "JSONP wrapping failed"})' in result


class TestProxyManager:
    """Тесты для менеджера прокси"""

    @pytest.fixture
    def proxy_manager(self):
        return ProxyManager()

    @pytest.mark.asyncio
    async def test_test_proxy_success(self, proxy_manager):
        """Тест успешной проверки прокси"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            result = await proxy_manager.test_proxy('http://proxy.example.com:8080')
            assert result is True

    @pytest.mark.asyncio
    async def test_test_proxy_failure(self, proxy_manager):
        """Тест неудачной проверки прокси"""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception(
                "Connection failed")

            result = await proxy_manager.test_proxy('http://proxy.example.com:8080')
            assert result is False


class TestRequestHandlers:
    """Тесты обработчиков запросов"""

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc(self):
        """Тест обработки enc запроса"""
        # Создаем тестовые данные в формате btoa
        test_params = "param/key1=value1/param/key2=value2/"
        test_url_part = "https://example.com/"
        encoded_data = test_params + test_url_part
        encoded_b64 = base64.b64encode(encoded_data.encode()).decode()
        encoded_url = urllib.parse.quote(encoded_b64)

        segments = ['enc', encoded_url, 'api', 'data']

        with patch('proxy_server.make_request') as mock_make_request:
            mock_make_request.return_value = {
                'currentUrl': 'https://example.com/api/data',
                'cookie': [],
                'headers': {},
                'status': 200,
                'body': 'success'
            }

            result = await handle_encoded_request(segments, 'GET')
            assert result['status'] == 200

            # Проверяем что параметры и URL правильно обработаны
            call_args = mock_make_request.call_args
            assert call_args[1]['params'] == {
                'key1': 'value1', 'key2': 'value2'}
            assert 'https://example.com/api/data' in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc1(self):
        """Тест обработки enc1 запроса"""
        # Создаем тестовые данные в формате btoa
        test_params = "param/key1=value1/"
        test_url_part = "https://example.com/api/"
        encoded_data = test_params + test_url_part
        encoded_b64 = base64.b64encode(encoded_data.encode()).decode()
        encoded_url = urllib.parse.quote(encoded_b64)

        segments = ['enc1', encoded_url, 'data']

        with patch('proxy_server.make_request') as mock_make_request:
            mock_make_request.return_value = {
                'currentUrl': 'https://example.com/api/data',
                'cookie': [],
                'headers': {},
                'status': 200,
                'body': 'success'
            }

            result = await handle_encoded_request(segments, 'GET')
            assert result['status'] == 200

            # Проверяем что параметры и URL правильно обработаны
            call_args = mock_make_request.call_args
            assert call_args[1]['params'] == {'key1': 'value1'}
            assert 'https://example.com/api/data' in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc2(self):
        """Тест обработки enc2 запроса"""
        # Создаем тестовые данные в формате btoa
        test_params = "param/key1=value1/"
        test_full_url = "https://example.com/api/data?query=test"
        encoded_data = test_params + test_full_url
        encoded_b64 = base64.b64encode(encoded_data.encode()).decode()
        encoded_url = urllib.parse.quote(encoded_b64)

        segments = ['enc2', encoded_url, 'ignored_segment']

        with patch('proxy_server.make_request') as mock_make_request:
            mock_make_request.return_value = {
                'currentUrl': 'https://example.com/api/data?query=test',
                'cookie': [],
                'headers': {},
                'status': 200,
                'body': 'success'
            }

            result = await handle_encoded_request(segments, 'GET')
            assert result['status'] == 200

            # Проверяем что параметры и полный URL правильно обработаны
            call_args = mock_make_request.call_args
            assert call_args[1]['params'] == {'key1': 'value1'}
            assert 'https://example.com/api/data?query=test' in call_args[0][0]

    @pytest.mark.asyncio
    async def test_handle_encoded_request_with_query_params(self):
        """Тест закодированного запроса с query параметрами"""
        test_params = "param/key1=value1/"
        test_url_part = "https://example.com/"
        encoded_data = test_params + test_url_part
        encoded_b64 = base64.b64encode(encoded_data.encode()).decode()
        encoded_url = urllib.parse.quote(encoded_b64)

        segments = ['enc', encoded_url, 'api', 'data']
        query_params = {'key2': 'value2', 'key3': 'value3'}

        with patch('proxy_server.make_request') as mock_make_request:
            mock_make_request.return_value = {
                'currentUrl': 'https://example.com/api/data',
                'cookie': [],
                'headers': {},
                'status': 200,
                'body': 'success'
            }

            result = await handle_encoded_request(segments, 'GET', query_params=query_params)
            assert result['status'] == 200

            # Проверяем что параметры объединились
            call_args = mock_make_request.call_args
            assert call_args[1]['params'] == {
                'key1': 'value1', 'key2': 'value2', 'key3': 'value3'}


class TestProxyRequestTypes:
    """Тесты различных типов прокси запросов"""

    @patch('proxy_server.handle_request')
    def test_enc_proxy_request(self, mock_handle_request):
        """Тест enc прокси запроса"""
        mock_handle_request.return_value = {
            'currentUrl': 'https://httpbin.org/json',
            'cookie': [],
            'headers': {'content-type': 'application/json'},
            'status': 200,
            'body': '{"test": "data"}'
        }

        # Создаем валидный encoded запрос
        test_data = "param/key=value/https://httpbin.org/"
        encoded = base64.b64encode(test_data.encode()).decode()
        encoded_url = urllib.parse.quote(encoded)

        response = client.get(f"/enc/{encoded_url}/json")
        assert response.status_code == 200

    @patch('proxy_server.handle_request')
    def test_enc1_proxy_request(self, mock_handle_request):
        """Тест enc1 прокси запроса"""
        mock_handle_request.return_value = {
            'currentUrl': 'https://api.example.com/data',
            'cookie': [],
            'headers': {},
            'status': 200,
            'body': '{"data": "test"}'
        }

        # Создаем валидный encoded запрос
        test_data = "param/key=value/https://api.example.com/"
        encoded = base64.b64encode(test_data.encode()).decode()
        encoded_url = urllib.parse.quote(encoded)

        response = client.get(f"/enc1/{encoded_url}/data")
        assert response.status_code == 200

    @patch('proxy_server.handle_request')
    def test_enc2_proxy_request(self, mock_handle_request):
        """Тест enc2 прокси запроса"""
        mock_handle_request.return_value = {
            'currentUrl': 'https://api.example.com/data',
            'cookie': [],
            'headers': {},
            'status': 200,
            'body': '{"data": "test"}'
        }

        # Создаем валидный encoded запрос
        test_data = "param/key=value/https://api.example.com/data"
        encoded = base64.b64encode(test_data.encode()).decode()
        encoded_url = urllib.parse.quote(encoded)

        response = client.get(f"/enc2/{encoded_url}/data")
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
