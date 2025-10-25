#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi.testclient import TestClient
import pytest
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Импортируем app только когда нужно


@pytest.fixture
def client():
    """Фикстура для тестового клиента FastAPI"""
    from src.proxy_server import app
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def event_loop():
    """Создает event loop для асинхронных тестов"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def setup_environment():
    """Настройка переменных окружения для тестов"""
    original_env = os.environ.copy()

    # Устанавливаем тестовые переменные окружения
    os.environ['LOG_LEVEL'] = 'ERROR'
    os.environ['USE_PROXY'] = 'false'
    os.environ['PROXY_TEST_URL'] = 'http://httpbin.org/ip'
    os.environ['PROXY_TEST_TIMEOUT'] = '5'
    os.environ['MAX_PROXY_RETRIES'] = '2'
    os.environ['MAX_REDIRECTS'] = '3'
    os.environ['STREAM_CHUNK_SIZE'] = '8192'
    os.environ['STREAM_TIMEOUT'] = '30'
    os.environ['TIMEOUT_CONNECT'] = '5'
    os.environ['TIMEOUT_READ'] = '10'
    os.environ['TIMEOUT_WRITE'] = '5'
    os.environ['TIMEOUT_POOL'] = '5'
    os.environ['MAX_RANGE_SIZE'] = '10485760'
    os.environ['MAX_REQUEST_SIZE'] = '1048576'
    os.environ['HEAD_REQUEST_TIMEOUT'] = '10'
    os.environ['PORT'] = '8080'

    yield

    # Восстанавливаем оригинальные переменные окружения
    os.environ.clear()
    os.environ.update(original_env)
