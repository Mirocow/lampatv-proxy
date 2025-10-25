#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import json
import logging
import urllib.parse
import re
import traceback
import random
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from httpx_socks import AsyncProxyTransport
import os
from datetime import datetime
from typing import List, Dict, Optional

# ==================== Configuration ====================

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=log_level,
    format='[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('lampa-proxy')

CONFIG = {
    'timeout': 30,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    'max_redirects': 10,
    'use_proxy': os.getenv('USE_PROXY', 'false').lower() == 'true',
    'proxy_list': [],
    'working_proxies': [],
    'proxy_test_url': os.getenv('PROXY_TEST_URL', 'http://httpbin.org/ip'),
    'proxy_test_timeout': int(os.getenv('PROXY_TEST_TIMEOUT', '10')),
    'max_proxy_retries': int(os.getenv('MAX_PROXY_RETRIES', '3'))
}

class ProxyManager:
    """Менеджер для работы с прокси"""

    def __init__(self):
        self.working_proxies = []
        self.proxy_stats = {}
        self.lock = asyncio.Lock()

    async def test_proxy(self, proxy: str) -> bool:
        """Проверка работоспособности прокси"""
        try:
            
            request_headers = {
                'User-Agent': CONFIG['user_agent'],
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,ru;q=0.7',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            }
            
            # Используем правильный формат для прокси в новой версии httpx
            timeout_config = httpx.Timeout(connect=300.0, read=300.0, write=300.0, pool=300.0)
            
            transport = AsyncProxyTransport.from_url(proxy)

            # Настройки для запроса
            init_params = {
                'headers': request_headers,
                'follow_redirects': True,
                'timeout': timeout_config,
                'transport': transport,
            }

            async with httpx.AsyncClient(**init_params) as client:

                # Используем несколько тестовых URL
                test_urls = [
                    "https://ifconfig.me/ip",
                    "http://httpbin.org/ip",
                    "http://api.ipify.org?format=json"
                ]

                for test_url in test_urls:
                    try:
                        logger.info(f"Testing proxy {proxy} with URL: {test_url}")
                        response = await client.get(test_url)

                        if response.status_code == 200:
                            try:
                                response_content_type = response.headers.get('content-type', '').lower()
                                if 'application/json' in response_content_type:
                                    data = response.json()
                                else:
                                    data = response.read()
                                    
                                logger.info(f"✓ Proxy {proxy} is working with {test_url},: {data}")

                            except:
                                logger.info(f"✗ Proxy test response text: {response.text[:200]}...")

                            return True

                        else:
                            logger.warning(f"Proxy {proxy} returned status {response.status_code} for {test_url}")

                    except Exception as e:
                        logger.warning(f"✗ Proxy {proxy} failed for {test_url}: {str(e)}")
                        continue

                # Если ни один URL не сработал
                logger.warning(f"✗ Proxy {proxy} failed for all test URLs")
                return False

        except httpx.ConnectError as e:
            logger.warning(f"✗ Proxy {proxy} connection error: {str(e)}")
            return False

        except httpx.TimeoutException:
            logger.warning(f"✗ Proxy {proxy} timeout")
            return False

        except Exception as e:
            logger.warning(f"✗ Proxy {proxy} unexpected error: {str(e)}")
            return False

    async def validate_proxies(self, proxies: List[str]) -> List[str]:
        """Проверка списка прокси и возврат рабочих"""
        
        logger.info(f"Validating {len(proxies)} proxies...")

        tasks = [self.test_proxy(proxy) for proxy in proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        working_proxies = []
        for i, result in enumerate(results):
            if result is True:
                working_proxies.append(proxies[i])
                self.proxy_stats[proxies[i]] = {
                    'success': 0, 'failures': 0, 'last_used': None}

        logger.info(f"Found {len(working_proxies)} working proxies out of {len(proxies)}")

        return working_proxies

    def get_random_proxy(self) -> Optional[str]:
        """Получение случайного рабочего прокси"""
        if not self.working_proxies:
            return None

        scored_proxies = []
        for proxy in self.working_proxies:
            stats = self.proxy_stats.get(proxy, {'success': 0, 'failures': 0})
            score = max(0, stats['success'] - stats['failures'] * 2)
            scored_proxies.append((proxy, score))

        total_score = sum(score for _, score in scored_proxies)
        if total_score == 0:
            return random.choice(self.working_proxies)

        rand_val = random.uniform(0, total_score)
        current = 0
        for proxy, score in scored_proxies:
            current += score
            if rand_val <= current:
                return proxy

        return random.choice(self.working_proxies)

    async def mark_proxy_success(self, proxy: str):
        """Отметить успешное использование прокси"""
        async with self.lock:
            if proxy in self.proxy_stats:
                self.proxy_stats[proxy]['success'] += 1
                self.proxy_stats[proxy]['last_used'] = datetime.now()

    async def mark_proxy_failure(self, proxy: str):
        """Отметить неудачное использование прокси"""
        async with self.lock:
            if proxy in self.proxy_stats:
                self.proxy_stats[proxy]['failures'] += 1

                if self.proxy_stats[proxy]['failures'] >= CONFIG['max_proxy_retries']:
                    if proxy in self.working_proxies:
                        self.working_proxies.remove(proxy)
                        logger.warning(f"Temporarily removed failing proxy: {proxy}")

    async def add_proxy(self, proxy: str):
        """Добавить прокси в список рабочих"""
        async with self.lock:
            if proxy not in self.working_proxies:
                self.working_proxies.append(proxy)
                if proxy not in self.proxy_stats:
                    self.proxy_stats[proxy] = {
                        'success': 0, 'failures': 0, 'last_used': None}
