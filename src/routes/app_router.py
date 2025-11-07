import base64
import json
from datetime import datetime
from typing import Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse

from src.models.interfaces import IRouter, IContentProcessor, IHttpClientFactory, IProxyManager, IConfig
from src.services.request_handler import RequestHandler
from src.models.responses import (
    HealthResponse, HttpFactoryInfoResponse, ProxyResponse, RootResponse,
    ErrorResponse, ProxyStatsResponse, EncodedRequestParams, ApiResponse, ApiInfoResponse
)


class AppRouter(IRouter):
    """Роутер приложения с поддержкой всех типов запросов"""

    def __init__(self, request_handler: RequestHandler, content_processor: IContentProcessor,
                 http_factory: IHttpClientFactory, proxy_manager: IProxyManager, config: IConfig):
        self.request_handler = request_handler
        self.content_processor = content_processor
        self.http_factory = http_factory
        self.proxy_manager = proxy_manager
        self.config = config
        self.logger = self.content_processor.logger

    def setup_routes(self, app):
        """Настройка маршрутов"""

        @app.get("/", response_model=RootResponse)
        async def root():
            return RootResponse(
                name="Lampa Proxy Server",
                version="3.2.1",
                description="Прокси сервер с поддержкой потокового видео, Range запросов и перемотки"
            )

        @app.get("/health", response_model=HealthResponse)
        async def health():
            return HealthResponse(
                status="healthy",
                timestamp=datetime.now().isoformat(),
                version="3.2.1"
            )

        @app.get("/info", response_model=ApiInfoResponse)
        async def stats():
            client_cache_info = self.http_factory.get_client_cache_info()

            return ApiInfoResponse(
                status="running",
                timestamp=datetime.now().isoformat(),
                config=self.config.to_dict(),
                http_client_factory=client_cache_info
            )


        @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
        async def proxy_request(request: Request, path: str):
            """Основной прокси-маршрут для обработки всех запросов с поддержкой enc/enc1/enc2/enc3"""
            try:
                # Пропускаем служебные эндпоинты
                if path in ["", "health", "stats", "favicon.ico"]:
                    return

                # Извлекаем заголовки запроса
                request_headers = {}
                for header in ['User-Agent', 'Accept', 'Content-Type', 'Origin', 'Referer', 'Cookie', 'Range', 'Authorization']:
                    if value := request.headers.get(header):
                        request_headers[header] = value

                # Логируем Range заголовок для отладки перемотки
                if 'Range' in request_headers:
                    self.logger.info(f"Client Range header: {request_headers['Range']}")

                post_data = None

                # Извлечение тела запроса
                if request.method in ["POST", "PUT", "DELETE"]:
                    try:
                        content_type = request.headers.get('content-type', '').lower()
                        if 'application/x-www-form-urlencoded' in content_type:
                            body = await request.body()
                            post_data = body.decode('utf-8')
                        elif 'multipart/form-data' in content_type:
                            form_data = await request.form()
                            post_data = dict(form_data)
                        elif 'application/json' in content_type:
                            post_data = await request.json()
                        else:
                            post_data = await request.body()
                    except Exception as e:
                        self.logger.error(f"Error reading request body: {str(e)}")
                        return JSONResponse(
                            content={'error': f'Failed to read request body: {str(e)}'},
                            status_code=400
                        )

                # Извлечение параметров запроса
                query_params = dict(request.query_params)

                # Обработка запроса через RequestHandler
                response_body, response_status, response_content_type = await self.request_handler.handle_request(
                    path,
                    request.method,
                    post_data,
                    query_params,
                    request_headers
                )

                # Если результат - StreamingResponse (видео), возвращаем его как есть
                if isinstance(response_body, StreamingResponse):
                    return response_body

                # Обработка ошибок
                if isinstance(response_body, dict) and 'error' in response_body:
                    return JSONResponse(
                        content=response_body,
                        status_code=response_status,
                        headers={'Access-Control-Allow-Origin': '*'}
                    )

                # Вывод всего объекта ProxyResponse
                if 'application/json' in response_content_type and isinstance(response_body, ProxyResponse):
                    return JSONResponse(
                        content=response_body.dict(),
                        status_code=response_status,
                        headers={'Access-Control-Allow-Origin': '*'}
                    )

                # Вывод тела сообщения
                if 'application/json' in response_content_type:
                    return JSONResponse(
                        content=response_body,
                        status_code=response_status,
                        headers={'Access-Control-Allow-Origin': '*'}
                    )

                return Response(
                    content=response_body if isinstance(response_body, bytes) else str(response_body).encode(),
                    status_code=response_status,
                    media_type=response_content_type,
                    headers={
                        'Access-Control-Allow-Origin': '*',
                        'Content-Type': response_content_type,
                    }
                )

            except HTTPException as e:
                # Обрабатываем HTTPException отдельно
                return JSONResponse(
                    status_code=e.status_code,
                    content={'error': e.detail},
                    headers={'Access-Control-Allow-Origin': '*'}
                )

            except Exception as e:
                self.logger.error(f"Proxy request error: {str(e)}")
                return JSONResponse(
                    status_code=500,
                    content={'error': f'Internal server error: {str(e)}'},
                    headers={'Access-Control-Allow-Origin': '*'}
                )

        @app.options("/{path:path}")
        async def options_handler():
            """Обработчик OPTIONS запросов для CORS"""
            return Response(headers={
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': '*',
                'Access-Control-Allow-Headers': '*'
            })

        @app.exception_handler(404)
        async def not_found_handler(request: Request, exc: HTTPException):
            return JSONResponse(
                status_code=404,
                content={"error": "Endpoint not found", "path": request.url.path}
            )

        @app.exception_handler(500)
        async def internal_error_handler(request: Request, exc: HTTPException):
            return JSONResponse(
                status_code=500,
                content={"error": "Internal server error"}
            )
