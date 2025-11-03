import asyncio
import logging
import re
from typing import Dict, Optional, Tuple, AsyncGenerator

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from src.models.interfaces import IVideoStreamer, IConfig, IHttpClientFactory, IContentInfoGetter, IProxyGenerator, ITimeoutConfigurator


class VideoStreamer(IVideoStreamer):
    """Потоковая передача видео"""

    def __init__(self, config: IConfig, http_factory: IHttpClientFactory,
                 content_getter: IContentInfoGetter, proxy_generator: IProxyGenerator,
                 timeout_configurator: ITimeoutConfigurator):
        self.config = config
        self.http_factory = http_factory
        self.content_getter = content_getter
        self.proxy_generator = proxy_generator
        self.timeout_configurator = timeout_configurator
        self.logger = logging.getLogger('lampa-proxy-video-streamer')

    async def stream_video(self,
                           target_url: str,
                           request_headers: Dict,
                           range_header: str = None) -> StreamingResponse:

        self.logger.info(
            f"Streaming video with range support from: {target_url}")
        self.logger.debug(f"Range header: {range_header}")

        content_info = await self.content_getter.get_content_info(target_url, request_headers, use_head=True)

        if content_info.error:
            raise HTTPException(
                status_code=500, detail=f"Failed to get video info: {content_info.error}")

        self.logger.info(
            f"Content info: status={content_info.status_code}, size={content_info.content_length}, type={content_info.content_type}")

        file_size = content_info.content_length
        content_type = content_info.content_type

        if file_size == 0:
            self.logger.warning(
                "File size is unknown, range requests may not work properly")

        start_byte, end_byte = self._parse_range_header(
            range_header, file_size)
        self.logger.info(
            f"Requested range: {start_byte}-{end_byte} (file size: {file_size})")

        range_requested = False
        if range_header or start_byte > 0 or (file_size > 0 and end_byte < file_size - 1):
            if file_size > 0:
                request_headers['Range'] = f'bytes={start_byte}-{end_byte}'
            else:
                request_headers['Range'] = f'bytes={start_byte}-'
            range_requested = True
            self.logger.info(
                f"Sending Range to source: {request_headers['Range']}")

        stream_generator = self._create_stream_generator(
            target_url, request_headers)
        response_headers = self._prepare_response_headers(
            content_type, range_requested, start_byte, end_byte, file_size)
        status_code = 206 if range_requested else 200

        return StreamingResponse(
            stream_generator,
            media_type=content_type,
            headers=response_headers,
            status_code=status_code
        )

    async def _create_stream_generator(self, target_url: str, request_headers: Dict) -> AsyncGenerator[bytes, None]:
        stream_active = True
        bytes_streamed = 0
        proxy = None

        try:
            proxy = await self.proxy_generator.get_proxy() if self.proxy_generator.has_proxies() else None

            timeout_multiplier = 10.0
            if proxy:
                timeout_multiplier = 30.0

            # Создаем таймаут для видео потока
            timeout = self.timeout_configurator.create_timeout_config(
                timeout_multiplier)

            # Создаем запрос с учетом параметров
            async with self.http_factory.create_client(
                headers=request_headers,
                is_video=True,
                follow_redirects=True,
                verify_ssl=False,
                proxy=proxy,
                timeout=timeout
            ) as client:

                async with client.stream('GET', target_url) as response:
                    self.logger.info(
                        f"Source response status: {response.status_code}")

                    if response.status_code == 404:
                        self.logger.error(
                            f"Video not found (404): {target_url}")
                        return
                    elif response.status_code == 416:
                        self.logger.error(
                            f"Range not satisfiable (416): {target_url}")
                        return
                    elif response.status_code >= 400:
                        self.logger.error(
                            f"Source server error {response.status_code}: {target_url}")
                        return

                    response_content_type = response.headers.get(
                        'content-type', '')
                    content_range = response.headers.get('content-range', '')
                    response_content_length = response.headers.get(
                        'content-length', 'unknown')

                    self.logger.info(
                        f"Video content-type: {response_content_type}")
                    self.logger.info(f"Content-Range: {content_range}")
                    self.logger.info(
                        f"Content-Length: {response_content_length}")

                    expected_bytes = self._get_expected_bytes(
                        content_range, response_content_length)

                    async for chunk in response.aiter_bytes(chunk_size=self.config.stream_chunk_size):
                        if not stream_active:
                            break

                        bytes_streamed += len(chunk)
                        self.logger.debug(
                            f"Streamed {bytes_streamed} bytes so far")

                        if expected_bytes > 0 and bytes_streamed >= expected_bytes:
                            self.logger.info(
                                f"Reached expected end of stream: {bytes_streamed}/{expected_bytes} bytes")
                            yield chunk
                            break

                        yield chunk

                    self.logger.info(
                        f"Video stream completed: {bytes_streamed} bytes streamed")

                    if proxy:
                        await self.proxy_generator.mark_success(proxy)

        except asyncio.CancelledError:
            self.logger.info("Video stream was cancelled by client")
        except Exception as e:
            self.logger.error(f"Video stream error: {str(e)}")
            if proxy:
                await self.proxy_generator.mark_failure(proxy)

    def _get_expected_bytes(self, content_range: str, response_content_length: str) -> int:
        if content_range:
            match = re.match(r'bytes\s+(\d+)-(\d+)/(\d+)', content_range)
            if match:
                range_start = int(match.group(1))
                range_end = int(match.group(2))
                expected_bytes = range_end - range_start + 1
                self.logger.info(
                    f"Expected bytes from Content-Range: {expected_bytes}")
                return expected_bytes

        elif response_content_length != 'unknown':
            try:
                expected_bytes = int(response_content_length)
                self.logger.info(
                    f"Expected bytes from Content-Length: {expected_bytes}")
                return expected_bytes
            except ValueError:
                pass

        return 0

    def _prepare_response_headers(self,
                                  content_type: str,
                                  range_requested: bool,
                                  start_byte: int,
                                  end_byte: int,
                                  file_size: int) -> Dict[str, str]:
        response_headers = {
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': '*',
            'Access-Control-Expose-Headers': 'Content-Length, Content-Range, Accept-Ranges',
            'Content-Type': content_type,
            'X-Content-Type-Options': 'nosniff',
        }

        if range_requested and file_size > 0:
            content_length = end_byte - start_byte + 1
            response_headers['Content-Range'] = f'bytes {start_byte}-{end_byte}/{file_size}'
            response_headers['Content-Length'] = str(content_length)
            self.logger.info(
                f"Sending 206 Partial Content: {content_length} bytes (range: {start_byte}-{end_byte})")
        elif not range_requested and file_size > 0:
            response_headers['Content-Length'] = str(file_size)
            self.logger.info(f"Sending 200 OK: {file_size} bytes")
        else:
            self.logger.info(
                "Sending response without Content-Length (unknown file size)")

        return response_headers

    def _parse_range_header(self, range_header: Optional[str], file_size: int) -> Tuple[int, int]:
        if not range_header:
            return 0, file_size - 1 if file_size > 0 else 0

        try:
            range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
            if not range_match:
                return 0, file_size - 1 if file_size > 0 else 0

            start = int(range_match.group(1))
            end_str = range_match.group(2)

            if end_str:
                end = int(end_str)
            else:
                end = file_size - 1 if file_size > 0 else 0

            if file_size > 0:
                if start < 0:
                    start = 0
                if start >= file_size:
                    start = file_size - 1
                    end = file_size - 1
                if end >= file_size:
                    end = file_size - 1
                if start > end:
                    start, end = end, start

            if file_size > 0 and (end - start) > self.config.max_range_size:
                end = start + self.config.max_range_size - 1
                if end >= file_size:
                    end = file_size - 1

            self.logger.debug(
                f"Parsed range: {start}-{end} (file size: {file_size})")
            return start, end

        except Exception as e:
            self.logger.error(
                f"Error parsing range header '{range_header}': {str(e)}")
            return 0, file_size - 1 if file_size > 0 else 0
