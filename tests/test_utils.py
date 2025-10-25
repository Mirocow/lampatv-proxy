#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from unittest.mock import AsyncMock, MagicMock


class AsyncTestCase:
    """Базовый класс для асинхронных тестов"""

    @staticmethod
    def async_test(coro):
        """Декоратор для асинхронных тестов"""
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro(*args, **kwargs))
        return wrapper


def create_mock_response(
    status_code=200,
    content_type="application/json",
    text="",
    headers=None,
    json_data=None
):
    """Создает mock HTTP response"""
    mock_response = AsyncMock()
    mock_response.status_code = status_code
    mock_response.headers = headers or {"content-type": content_type}
    mock_response.text = text
    mock_response.read.return_value = text.encode() if text else b""

    if json_data:
        mock_response.json.return_value = json_data
        mock_response.text = str(json_data)

    return mock_response


def create_mock_stream_response(chunks=None):
    """Создает mock streaming response"""
    if chunks is None:
        chunks = [b"chunk1", b"chunk2", b"chunk3"]

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "video/mp4"}

    async def chunk_generator():
        for chunk in chunks:
            yield chunk

    mock_response.aiter_bytes.return_value = chunk_generator()
    return mock_response
