from typing import Dict, Any, Optional, Tuple, Union
import json
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, Response

from src.utils.logger import get_logger
from src.models.interfaces import IContentProcessor, IConfig
from src.utils.url_utils import (
    decode_base64_url, parse_encoded_data, build_url,
    is_valid_json, parse_range_header
)
from src.models.responses import ProxyResponse


class RequestHandler:
    """Обработчик запросов с поддержкой всех типов кодирования"""

    def __init__(self,
                 content_processor: IContentProcessor,
                 config: IConfig):
        self.content_processor = content_processor
        self.config = config
        self.logger = get_logger('request-handler', self.config.log_level)

    async def handle_request(
        self,
        path: str,
        method: str = 'GET',
        post_data: Any = None,
        query_params: Optional[Dict] = None,
        request_headers: Optional[Dict] = None
    ) -> Tuple[Any, int, str]:
        """Основной обработчик запросов"""
        if request_headers is None:
            request_headers = {}
        if query_params is None:
            query_params = {}

        segments = [s for s in path.strip('/').split('/') if s]
        self.logger.info(f"Handling {method} request: /{path}")

        if not segments:
            return {'error': 'Empty request path'}, 400, 'application/json'

        handler_type = segments[0]
        self.logger.info(f"Using handler: {handler_type}")

        try:
            if handler_type in ['enc', 'enc1', 'enc2', 'enc3']:
                response = await self._handle_encoded_request(
                    segments,
                    method,
                    post_data,
                    query_params,
                    request_headers)
            else:
                response = await self._handle_direct_request(
                    path,
                    method,
                    post_data,
                    query_params,
                    request_headers)

            return response

        except HTTPException:
            raise
        except Exception as e:
            self.logger.error(f"Request handling error: {str(e)}")
            return {'error': f'Internal server error: {str(e)}'}, 500, 'application/json'

    async def _handle_encoded_request(
        self,
        segments: list,
        method: str,
        post_data: Any,
        query_params: Dict,
        request_headers: Dict
    ) -> Tuple[Any, int, str]:
        """Обработка закодированных запросов (enc/enc1/enc2/enc3)"""
        self.logger.info(f"Processing encoded {method} request with {len(segments)} segments")

        if len(segments) < 2:
            raise ValueError("Invalid encoded request - not enough segments")

        encoded_part = segments[1]
        additional_segments = segments[2:]
        handler_type = segments[0]

        # Декодируем base64 данные
        decoded_data = decode_base64_url(encoded_part)
        self.logger.info(f"Decoded data: {decoded_data} from encoded: {handler_type}")

        # Парсим параметры из декодированных данных
        encoded_params, url_segments_from_encoded = parse_encoded_data(decoded_data)

        # Определяем целевой URL в зависимости от типа кодирования
        target_url = ""

        if handler_type in ['enc', 'enc1', 'enc3']:
            if not additional_segments:
                raise ValueError("No URL found in encoded data for enc")

            target_url = build_url(additional_segments, query_params)

        elif handler_type == 'enc2':
            if not url_segments_from_encoded:
                raise ValueError("No URL found in encoded data for enc2")

            for param in additional_segments:
                try:
                    # Декодируем base64 данные
                    decoded_data = decode_base64_url(param)
                    if decoded_data:
                        # Безопасное разбиение на параметры
                        new_params = {}
                        for pair in decoded_data.split('&'):
                            if '=' in pair:
                                key, value = pair.split('=', 1)
                                new_params[key] = value
                            else:
                                # Обработка параметров без значения
                                new_params[pair] = None

                        query_params = {**query_params, **new_params}

                except Exception as e:
                    continue

            target_url = build_url(url_segments_from_encoded, query_params)

        if isinstance(encoded_params, dict):
            for key in ['User-Agent', 'Origin', 'Referer', 'Cookie', 'Content-Type', 'Accept',
                        'x-csrf-token', 'Sec-Fetch-Dest', 'Sec-Fetch-Mode', 'Sec-Fetch-Site',
                        'Authorization', 'Range']:
                if key in encoded_params:
                    request_headers[key] = encoded_params[key]

        self.logger.info(f"Proxying {method} with encode type {handler_type} request to: {target_url}")

        # Обработка Range заголовка для видео
        range_header = request_headers.get('Range')

        # Отправка запроса через ContentProcessor
        result = await self.content_processor.process_content(
            target_url=target_url,
            method=method,
            data=post_data,
            headers=request_headers,
            range_header=range_header
        )

        # Обработка результата в зависимости от типа кодирования
        if isinstance(result, StreamingResponse):
            return result, 200, ''

        if isinstance(result, ProxyResponse):
            response_content_type = result.headers.get('content-type', '').lower()
            response_body = result.body
            response_status = result.status

            if handler_type in ['enc', 'enc1', 'enc2']:
                if 'application/json' in response_content_type and is_valid_json(response_body):
                    response_body = json.loads(response_body)

            elif handler_type == 'enc3':
                if 'text/html' in response_content_type or 'text/plain' in response_content_type and is_valid_json(response_body):
                    response_content_type = 'application/json'
                    response_body = result

                elif 'application/json' in response_content_type:
                    response_body = result

            return response_body, response_status, response_content_type

        return result, 500, 'application/octet-stream'

    async def _handle_direct_request(
        self,
        path: str,
        method: str,
        post_data: Any,
        query_params: Dict,
        request_headers: Dict
    ) -> Tuple[Any, int, str]:
        """Обработка прямых URL запросов"""
        target_url = build_url([path], query_params)

        self.logger.info(f"Proxying {method} request to: {target_url}")

        # Обработка Range заголовка
        range_header = request_headers.get('Range')

        result = await self.content_processor.process_content(
            target_url=target_url,
            method=method,
            data=post_data,
            headers=request_headers,
            range_header=range_header
        )

        if isinstance(result, StreamingResponse):
            return result, 200, ''

        if isinstance(result, ProxyResponse):
            content_type = result.headers.get('content-type', '').lower()
            return result.body, result.status, content_type

        return result, 500, 'application/octet-stream'
