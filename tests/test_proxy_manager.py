#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from src.proxy_manager import ProxyManager
import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestProxyManager:
    """Тесты для ProxyManager"""

    @pytest.fixture
    def proxy_manager(self):
        return ProxyManager()

    @pytest.mark.asyncio
    async def test_init(self, proxy_manager):
        """Тест инициализации ProxyManager"""
        assert proxy_manager.working_proxies == []
        assert proxy_manager.proxy_stats == {}
        assert hasattr(proxy_manager, 'lock')


    @pytest.mark.asyncio
    async def test_test_proxy_success(self, proxy_manager):
        """Тест успешной проверки прокси"""
        test_proxy = "http://working-proxy:8080"

        # Create proper async mock response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.json.return_value = {'ip': 'test-ip'}

        # Create proper async context manager
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client  # Client returns itself on enter
        mock_client.__aexit__.return_value = None
        mock_client.get.return_value = mock_response

        with patch('src.proxy_manager.httpx.AsyncClient', return_value=mock_client):
            result = await proxy_manager.test_proxy(test_proxy)
            assert result is True

            # Verify the mock was called properly
            mock_client.get.assert_called()

    @pytest.mark.asyncio
    async def test_test_proxy_failure(self, proxy_manager):
        """Тест неудачной проверки прокси"""
        test_proxy = "http://failing-proxy:8080"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.side_effect = Exception("Connection failed")

        with patch('src.proxy_manager.httpx.AsyncClient', return_value=mock_client):
            result = await proxy_manager.test_proxy(test_proxy)
            assert result is False

    @pytest.mark.asyncio
    async def test_validate_proxies(self, proxy_manager):
        """Тест валидации списка прокси"""
        sample_proxies = ["proxy1", "proxy2", "proxy3"]

        with patch.object(proxy_manager, 'test_proxy') as mock_test:
            mock_test.side_effect = [True, False, True]

            working_proxies = await proxy_manager.validate_proxies(sample_proxies)

            assert len(working_proxies) == 2
            assert "proxy1" in working_proxies
            assert "proxy3" in working_proxies

    def test_get_random_proxy_empty(self, proxy_manager):
        """Тест получения случайного прокси из пустого списка"""
        assert proxy_manager.get_random_proxy() is None

    def test_get_random_proxy_with_proxies(self, proxy_manager):
        """Тест получения случайного прокси из непустого списка"""
        proxy_manager.working_proxies = ["proxy1", "proxy2", "proxy3"]

        proxy = proxy_manager.get_random_proxy()
        assert proxy in proxy_manager.working_proxies

    @pytest.mark.asyncio
    async def test_mark_proxy_success(self, proxy_manager):
        """Тест отметки успешного использования прокси"""
        proxy = "http://test-proxy:8080"
        proxy_manager.working_proxies = [proxy]
        proxy_manager.proxy_stats[proxy] = {
            "success": 0, "failures": 0, "last_used": None}

        await proxy_manager.mark_proxy_success(proxy)

        assert proxy_manager.proxy_stats[proxy]["success"] == 1

    @pytest.mark.asyncio
    async def test_mark_proxy_failure(self, proxy_manager):
        """Тест отметки неудачного использования прокси"""
        proxy = "http://test-proxy:8080"
        proxy_manager.working_proxies = [proxy]
        proxy_manager.proxy_stats[proxy] = {
            "success": 2, "failures": 1, "last_used": None}

        # Устанавливаем max_proxy_retries в 3, чтобы прокси не удалялся сразу
        with patch('src.proxy_manager.CONFIG') as mock_config:
            mock_config.__getitem__.return_value = 3

            await proxy_manager.mark_proxy_failure(proxy)

            assert proxy_manager.proxy_stats[proxy]["failures"] == 2
            # Прокси должен остаться в working_proxies
            assert proxy in proxy_manager.working_proxies

    @pytest.mark.asyncio
    async def test_mark_proxy_failure_removal(self, proxy_manager):
        """Тест удаления прокси при превышении лимита неудач"""
        proxy = "http://test-proxy:8080"
        proxy_manager.working_proxies = [proxy]
        proxy_manager.proxy_stats[proxy] = {
            "success": 1, "failures": 2, "last_used": None}

        # Устанавливаем max_proxy_retries в 3, но текущие failures уже 2
        # После вызова mark_proxy_failure failures станет 3, что равно max_proxy_retries
        with patch('src.proxy_manager.CONFIG') as mock_config:
            mock_config.__getitem__.return_value = 3

            await proxy_manager.mark_proxy_failure(proxy)

            assert proxy_manager.proxy_stats[proxy]["failures"] == 3
            # Прокси должен быть удален из working_proxies
            assert proxy not in proxy_manager.working_proxies

    @pytest.mark.asyncio
    async def test_add_proxy(self, proxy_manager):
        """Тест добавления прокси"""
        proxy = "http://new-proxy:8080"

        await proxy_manager.add_proxy(proxy)

        assert proxy in proxy_manager.working_proxies
        assert proxy in proxy_manager.proxy_stats

    @pytest.mark.asyncio
    async def test_add_proxy_duplicate(self, proxy_manager):
        """Тест добавления дублирующегося прокси"""
        proxy = "http://existing-proxy:8080"
        proxy_manager.working_proxies = [proxy]
        proxy_manager.proxy_stats[proxy] = {
            "success": 5, "failures": 1, "last_used": None}

        await proxy_manager.add_proxy(proxy)

        # Статистика не должна сбрасываться
        assert proxy_manager.proxy_stats[proxy]["success"] == 5
        assert proxy_manager.proxy_stats[proxy]["failures"] == 1
