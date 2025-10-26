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


class TestEdgeCases:
    """Тесты крайних случаев"""


    def test_range_parsing_edge_cases(self):
        """Тест парсинга крайних случаев Range заголовков"""
        edge_cases = [
            ("bytes=0-0", 1000, (0, 0)),  # один байт
            ("bytes=999-999", 1000, (999, 999)),  # последний байт
            ("bytes=0-", 0, (0, 50*1024*1024-1)),  # unknown size with start
            ("bytes=", 1000, (0, 999)),  # empty range
            ("bytes=100-50", 1000, (50, 99)),  # reversed range
        ]

        for range_header, file_size, expected in edge_cases:
            start, end = parse_range_header(range_header, file_size)
            assert (start, end) == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
