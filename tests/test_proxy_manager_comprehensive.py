#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from src.proxy_manager import ProxyManager
import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestProxyManagerComprehensive:
    """Комплексные тесты для ProxyManager для 100% покрытия"""

    @pytest.fixture
    def proxy_manager(self):
        return ProxyManager()

    @pytest.mark.asyncio
    async def test_test_proxy_connect_error(self):
        """Тест обработки ConnectError при проверке прокси"""
        proxy_manager = ProxyManager()
        test_proxy = "http://failing-proxy:8080"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        # Имитируем разные типы ошибок
        with patch('src.proxy_manager.httpx.AsyncClient', return_value=mock_client):
            # Тест с ConnectError
            mock_client.get.side_effect = Exception("Connection failed")
            result = await proxy_manager.test_proxy(test_proxy)
            assert result is False

    @pytest.mark.asyncio
    async def test_test_proxy_timeout_exception(self):
        """Тест обработки TimeoutException при проверке прокси"""
        proxy_manager = ProxyManager()
        test_proxy = "http://timeout-proxy:8080"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch('src.proxy_manager.httpx.AsyncClient', return_value=mock_client):
            # Тест с TimeoutException
            mock_client.get.side_effect = asyncio.TimeoutError()
            result = await proxy_manager.test_proxy(test_proxy)
            assert result is False

    @pytest.mark.asyncio
    async def test_test_proxy_http_status_error(self):
        """Тест обработки HTTPStatusError при проверке прокси"""
        proxy_manager = ProxyManager()
        test_proxy = "http://bad-status-proxy:8080"

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.headers = {'content-type': 'application/json'}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_response

        with patch('src.proxy_manager.httpx.AsyncClient', return_value=mock_client):
            result = await proxy_manager.test_proxy(test_proxy)
            # Должен вернуть False при статусе 500
            assert result is False

    @pytest.mark.asyncio
    async def test_test_proxy_success_with_different_test_urls(self):
        """Тест успешной проверки прокси с разными тестовыми URL"""
        proxy_manager = ProxyManager()
        test_proxy = "http://working-proxy:8080"

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {'ip': 'test-ip'}
        mock_response.read.return_value = b'test data'

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_response

        with patch('src.proxy_manager.httpx.AsyncClient', return_value=mock_client):
            result = await proxy_manager.test_proxy(test_proxy)
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_proxies_with_mixed_results(self):
        """Тест валидации прокси со смешанными результатами"""
        proxy_manager = ProxyManager()
        sample_proxies = ["proxy1", "proxy2", "proxy3", "proxy4"]

        with patch.object(proxy_manager, 'test_proxy') as mock_test:
            mock_test.side_effect = [
                True, False, Exception("Test error"), True]

            working_proxies = await proxy_manager.validate_proxies(sample_proxies)

            assert len(working_proxies) == 2
            assert "proxy1" in working_proxies
            assert "proxy4" in working_proxies
            assert "proxy2" not in working_proxies
            assert "proxy3" not in working_proxies

    def test_get_random_proxy_with_empty_stats(self):
        """Тест получения случайного прокси с пустой статистикой"""
        proxy_manager = ProxyManager()
        proxy_manager.working_proxies = ["proxy1", "proxy2", "proxy3"]

        # Не добавляем статистику, чтобы проверить fallback
        proxy = proxy_manager.get_random_proxy()
        assert proxy in proxy_manager.working_proxies

    def test_get_random_proxy_with_zero_scores(self):
        """Тест получения случайного прокси с нулевыми оценками"""
        proxy_manager = ProxyManager()
        proxy_manager.working_proxies = ["proxy1", "proxy2"]
        proxy_manager.proxy_stats = {
            "proxy1": {"success": 0, "failures": 0, "last_used": None},
            "proxy2": {"success": 0, "failures": 0, "last_used": None}
        }

        proxy = proxy_manager.get_random_proxy()
        assert proxy in proxy_manager.working_proxies

    @pytest.mark.asyncio
    async def test_mark_proxy_failure_not_in_stats(self):
        """Тест отметки неудачи для прокси, которого нет в статистике"""
        proxy_manager = ProxyManager()
        proxy = "http://unknown-proxy:8080"

        # Прокси нет в working_proxies и proxy_stats
        await proxy_manager.mark_proxy_failure(proxy)

        # Не должно быть ошибки, просто ничего не происходит
        assert proxy not in proxy_manager.working_proxies
        assert proxy not in proxy_manager.proxy_stats

    @pytest.mark.asyncio
    async def test_mark_proxy_success_not_in_stats(self):
        """Тест отметки успеха для прокси, которого нет в статистике"""
        proxy_manager = ProxyManager()
        proxy = "http://unknown-proxy:8080"

        # Прокси нет в working_proxies и proxy_stats
        await proxy_manager.mark_proxy_success(proxy)

        # Прокси должен быть добавлен
        assert proxy in proxy_manager.working_proxies
        assert proxy in proxy_manager.proxy_stats

    @pytest.mark.asyncio
    async def test_concurrent_access_to_proxy_manager(self):
        """Тест конкурентного доступа к ProxyManager"""
        proxy_manager = ProxyManager()

        async def add_proxy_task(proxy_name):
            await proxy_manager.add_proxy(proxy_name)
            await proxy_manager.mark_proxy_success(proxy_name)
            await proxy_manager.mark_proxy_failure(proxy_name)

        # Создаем несколько задач для конкурентного доступа
        tasks = [
            add_proxy_task(f"proxy{i}") for i in range(5)
        ]

        await asyncio.gather(*tasks)

        assert len(proxy_manager.working_proxies) == 5
        assert all(f"proxy{i}" in proxy_manager.proxy_stats for i in range(5))
