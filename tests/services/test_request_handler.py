import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, Tuple
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, Response

from src.models.interfaces import IContentProcessor, IConfig
from src.models.responses import ProxyResponse
from src.services.request_handler import RequestHandler


class TestRequestHandler:
    """Тесты для RequestHandler"""

    @pytest.fixture
    def mock_dependencies(self):
        """Создает моки всех зависимостей"""
        content_processor = Mock(spec=IContentProcessor)
        config = Mock(spec=IConfig)

        return {
            'content_processor': content_processor,
            'config': config
        }

    @pytest.fixture
    def request_handler(self, mock_dependencies):
        """Создает экземпляр RequestHandler с моками зависимостей"""
        return RequestHandler(**mock_dependencies)

    def test_initialization(self, mock_dependencies):
        """Тест инициализации RequestHandler"""
        # Act
        handler = RequestHandler(**mock_dependencies)

        # Assert
        assert handler.content_processor == mock_dependencies['content_processor']
        assert handler.config == mock_dependencies['config']
        assert handler.logger.name == 'lampa-proxy-request-handler'

    @pytest.mark.asyncio
    async def test_handle_request_empty_path(self, request_handler, caplog):
        """Тест обработки запроса с пустым путем"""
        # Arrange
        path = ""

        # Act
        with caplog.at_level('INFO'):
            result = await request_handler.handle_request(path)

        # Assert
        assert result[0] == {'error': 'Empty request path'}
        assert result[1] == 400
        assert result[2] == 'application/json'

    @pytest.mark.asyncio
    async def test_handle_request_direct_handler(self, request_handler, mock_dependencies, caplog):
        """Тест обработки прямого запроса"""
        # Arrange
        path = "https://example.com/api/data"
        method = "GET"

        # Мокируем прямой обработчик
        request_handler._handle_direct_request = AsyncMock(return_value=({"data": "test"}, 200, "application/json"))

        # Act
        with caplog.at_level('INFO'):
            result = await request_handler.handle_request(path, method)

        # Assert
        assert result == ({"data": "test"}, 200, "application/json")
        assert f"Handling {method} request: /{path}" in caplog.text
        request_handler._handle_direct_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_request_encoded_handler_enc(self, request_handler, caplog):
        """Тест обработки закодированного запроса типа enc"""
        # Arrange
        path = "enc/encoded_data/segment1/segment2"
        method = "GET"

        # Мокируем обработчик закодированных запросов
        request_handler._handle_encoded_request = AsyncMock(return_value=({"result": "success"}, 200, "application/json"))

        # Act
        with caplog.at_level('INFO'):
            result = await request_handler.handle_request(path, method)

        # Assert
        assert result == ({"result": "success"}, 200, "application/json")
        assert "Using handler: enc" in caplog.text
        request_handler._handle_encoded_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_request_encoded_handler_enc1(self, request_handler, caplog):
        """Тест обработки закодированного запроса типа enc1"""
        # Arrange
        path = "enc1/encoded_data/segment1"

        request_handler._handle_encoded_request = AsyncMock(return_value=({"result": "success"}, 200, "application/json"))

        # Act
        with caplog.at_level('INFO'):
            result = await request_handler.handle_request(path)

        # Assert
        assert result == ({"result": "success"}, 200, "application/json")
        assert "Using handler: enc1" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_request_encoded_handler_enc2(self, request_handler, caplog):
        """Тест обработки закодированного запроса типа enc2"""
        # Arrange
        path = "enc2/encoded_data"

        request_handler._handle_encoded_request = AsyncMock(return_value=({"result": "success"}, 200, "application/json"))

        # Act
        with caplog.at_level('INFO'):
            result = await request_handler.handle_request(path)

        # Assert
        assert result == ({"result": "success"}, 200, "application/json")
        assert "Using handler: enc2" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_request_encoded_handler_enc3(self, request_handler, caplog):
        """Тест обработки закодированного запроса типа enc3"""
        # Arrange
        path = "enc3/encoded_data/segment1"

        request_handler._handle_encoded_request = AsyncMock(return_value=({"result": "success"}, 200, "application/json"))

        # Act
        with caplog.at_level('INFO'):
            result = await request_handler.handle_request(path)

        # Assert
        assert result == ({"result": "success"}, 200, "application/json")
        assert "Using handler: enc3" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_request_http_exception(self, request_handler):
        """Тест обработки HTTPException"""
        # Arrange
        path = "enc/encoded_data"
        request_handler._handle_encoded_request = AsyncMock(side_effect=HTTPException(status_code=404, detail="Not found"))

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await request_handler.handle_request(path)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_handle_request_general_exception(self, request_handler, caplog):
        """Тест обработки общего исключения"""
        # Arrange
        path = "enc/encoded_data"
        request_handler._handle_encoded_request = AsyncMock(side_effect=Exception("Unexpected error"))

        # Act
        with caplog.at_level('ERROR'):
            result = await request_handler.handle_request(path)

        # Assert
        assert result[0] == {'error': 'Internal server error: Unexpected error'}
        assert result[1] == 500
        assert result[2] == 'application/json'
        assert "Request handling error: Unexpected error" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_encoded_request_insufficient_segments(self, request_handler, caplog):
        """Тест обработки закодированного запроса с недостаточным количеством сегментов"""
        # Arrange
        segments = ["enc"]

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

        assert "Invalid encoded request - not enough segments" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc_type_no_additional_segments(self, request_handler, caplog):
        """Тест обработки enc/enc1/enc3 без дополнительных сегментов"""
        # Arrange
        segments = ["enc", "encoded_data"]

        # Мокируем декодирование
        with patch('src.services.request_handler.decode_base64_url', return_value="decoded_data"):
            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, [])):
                # Act & Assert
                with pytest.raises(ValueError) as exc_info:
                    await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

                assert "No URL found in encoded data for enc" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc2_no_url_segments(self, request_handler, caplog):
        """Тест обработки enc2 без URL сегментов в закодированных данных"""
        # Arrange
        segments = ["enc2", "encoded_data"]

        # Мокируем декодирование
        with patch('src.services.request_handler.decode_base64_url', return_value="decoded_data"):
            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, [])):
                # Act & Assert
                with pytest.raises(ValueError) as exc_info:
                    await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

                assert "No URL found in encoded data for enc2" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc_type_with_headers(self, request_handler, mock_dependencies):
        """Тест обработки enc типа с заголовками из закодированных данных"""
        # Arrange
        segments = ["enc", "encoded_data", "segment1", "segment2"]
        request_headers = {"Existing": "header"}

        encoded_params = {
            "User-Agent": "test-agent",
            "Authorization": "Bearer token",
            "Range": "bytes=0-1000"
        }

        # Мокируем утилиты
        with patch('src.services.request_handler.decode_base64_url', return_value="decoded_data"):
            with patch('src.services.request_handler.parse_encoded_data', return_value=(encoded_params, [])):
                with patch('src.services.request_handler.build_url', return_value="https://target.com"):
                    # Мокируем процессор контента
                    proxy_response = ProxyResponse(
                        status=200,
                        body=b'{"result": "success"}',
                        headers={"content-type": "application/json"}
                    )
                    mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

                    # Act
                    result = await request_handler._handle_encoded_request(segments, "GET", None, {}, request_headers)

        # Assert
        assert request_headers["User-Agent"] == "test-agent"
        assert request_headers["Authorization"] == "Bearer token"
        assert request_headers["Range"] == "bytes=0-1000"
        assert request_headers["Existing"] == "header"

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc2_with_additional_params(self, request_handler, mock_dependencies):
        """Тест обработки enc2 с дополнительными параметрами"""
        # Arrange
        segments = ["enc2", "encoded_data", "additional_param"]
        query_params = {"existing": "param"}

        # Мокируем утилиты
        with patch('src.services.request_handler.decode_base64_url') as mock_decode:
            mock_decode.side_effect = [
                "decoded_main",  # Первый вызов для encoded_data
                "key1=value1&key2=value2"  # Второй вызов для additional_param
            ]

            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, ["url", "segment"])):
                with patch('src.services.request_handler.build_url', return_value="https://target.com"):
                    # Мокируем процессор контента
                    proxy_response = ProxyResponse(
                        status=200,
                        body=b'{"result": "success"}',
                        headers={"content-type": "application/json"}
                    )
                    mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

                    # Act
                    await request_handler._handle_encoded_request(segments, "GET", None, query_params, {})

        # Assert
        assert query_params["existing"] == "param"
        assert query_params["key1"] == "value1"
        assert query_params["key2"] == "value2"

    @pytest.mark.asyncio
    async def test_handle_encoded_request_streaming_response(self, request_handler, mock_dependencies):
        """Тест обработки StreamingResponse"""
        # Arrange
        segments = ["enc", "encoded_data", "segment1"]

        # Мокируем утилиты
        with patch('src.services.request_handler.decode_base64_url', return_value="decoded_data"):
            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, [])):
                with patch('src.services.request_handler.build_url', return_value="https://target.com"):
                    # Создаем мок StreamingResponse
                    streaming_response = Mock(spec=StreamingResponse)
                    mock_dependencies['content_processor'].process_content = AsyncMock(return_value=streaming_response)

                    # Act
                    result = await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

        # Assert
        assert result == (streaming_response, 200, '')

    @pytest.mark.asyncio
    async def test_handle_encoded_request_proxy_response_json_enc(self, request_handler, mock_dependencies):
        """Тест обработки ProxyResponse с JSON для enc типа"""
        # Arrange
        segments = ["enc", "encoded_data", "segment1"]

        # Мокируем утилиты
        with patch('src.services.request_handler.decode_base64_url', return_value="decoded_data"):
            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, [])):
                with patch('src.services.request_handler.build_url', return_value="https://target.com"):
                    with patch('src.services.request_handler.is_valid_json', return_value=True):
                        # Мокируем процессор контента
                        proxy_response = ProxyResponse(
                            status=200,
                            body=b'{"result": "success"}',
                            headers={"content-type": "application/json"}
                        )
                        mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

                        # Act
                        result = await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

        # Assert
        assert result[0] == {"result": "success"}  # Должен быть распарсен как JSON
        assert result[1] == 200
        assert result[2] == "application/json"

    @pytest.mark.asyncio
    async def test_handle_encoded_request_proxy_response_json_enc3(self, request_handler, mock_dependencies):
        """Тест обработки ProxyResponse с JSON для enc3 типа"""
        # Arrange
        segments = ["enc3", "encoded_data", "segment1"]

        # Мокируем утилиты
        with patch('src.services.request_handler.decode_base64_url', return_value="decoded_data"):
            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, [])):
                with patch('src.services.request_handler.build_url', return_value="https://target.com"):
                    with patch('src.services.request_handler.is_valid_json', return_value=True):
                        # Мокируем процессор контента
                        proxy_response = ProxyResponse(
                            status=200,
                            body=b'{"result": "success"}',
                            headers={"content-type": "text/html"}  # text/html но валидный JSON
                        )
                        mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

                        # Act
                        result = await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

        # Assert
        assert result[0] == proxy_response  # Для enc3 возвращается как есть
        assert result[1] == 200
        assert result[2] == "text/html"

    @pytest.mark.asyncio
    async def test_handle_encoded_request_proxy_response_binary(self, request_handler, mock_dependencies):
        """Тест обработки ProxyResponse с бинарными данными"""
        # Arrange
        segments = ["enc", "encoded_data", "segment1"]

        # Мокируем утилиты
        with patch('src.services.request_handler.decode_base64_url', return_value="decoded_data"):
            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, [])):
                with patch('src.services.request_handler.build_url', return_value="https://target.com"):
                    # Мокируем процессор контента
                    proxy_response = ProxyResponse(
                        status=200,
                        body=b'binary_data',
                        headers={"content-type": "application/octet-stream"}
                    )
                    mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

                    # Act
                    result = await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

        # Assert
        assert result[0] == b'binary_data'  # Должен остаться байтами
        assert result[1] == 200
        assert result[2] == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_handle_encoded_request_unknown_result_type(self, request_handler, mock_dependencies):
        """Тест обработки неизвестного типа результата"""
        # Arrange
        segments = ["enc", "encoded_data", "segment1"]

        # Мокируем утилиты
        with patch('src.services.request_handler.decode_base64_url', return_value="decoded_data"):
            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, [])):
                with patch('src.services.request_handler.build_url', return_value="https://target.com"):
                    # Мокируем процессор контента возвращающий неизвестный тип
                    mock_dependencies['content_processor'].process_content = AsyncMock(return_value="unknown_result")

                    # Act
                    result = await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

        # Assert
        assert result == ("unknown_result", 500, 'application/octet-stream')

    @pytest.mark.asyncio
    async def test_handle_direct_request(self, request_handler, mock_dependencies):
        """Тест обработки прямого запроса"""
        # Arrange
        path = "https://example.com/api/data"
        query_params = {"param": "value"}
        request_headers = {"User-Agent": "test"}

        # Мокируем утилиты
        with patch('src.services.request_handler.build_url', return_value="https://example.com/api/data?param=value"):
            # Мокируем процессор контента
            proxy_response = ProxyResponse(
                status=200,
                body=b'response_data',
                headers={"content-type": "text/plain"}
            )
            mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

            # Act
            result = await request_handler._handle_direct_request(path, "GET", None, query_params, request_headers)

        # Assert
        assert result == (b'response_data', 200, "text/plain")
        mock_dependencies['content_processor'].process_content.assert_called_once_with(
            target_url="https://example.com/api/data?param=value",
            method="GET",
            data=None,
            headers=request_headers,
            range_header=None
        )

    @pytest.mark.asyncio
    async def test_handle_direct_request_with_range_header(self, request_handler, mock_dependencies):
        """Тест обработки прямого запроса с Range заголовком"""
        # Arrange
        path = "https://example.com/video.mp4"
        request_headers = {"Range": "bytes=0-1000"}

        # Мокируем утилиты
        with patch('src.services.request_handler.build_url', return_value="https://example.com/video.mp4"):
            # Мокируем процессор контента
            proxy_response = ProxyResponse(
                status=206,
                body=b'video_data',
                headers={"content-type": "video/mp4"}
            )
            mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

            # Act
            result = await request_handler._handle_direct_request(path, "GET", None, {}, request_headers)

        # Assert
        assert result == (b'video_data', 206, "video/mp4")
        mock_dependencies['content_processor'].process_content.assert_called_once_with(
            target_url="https://example.com/video.mp4",
            method="GET",
            data=None,
            headers=request_headers,
            range_header="bytes=0-1000"
        )

    @pytest.mark.asyncio
    async def test_handle_direct_request_streaming_response(self, request_handler, mock_dependencies):
        """Тест обработки StreamingResponse в прямом запросе"""
        # Arrange
        path = "https://example.com/video.mp4"

        # Мокируем утилиты
        with patch('src.services.request_handler.build_url', return_value="https://example.com/video.mp4"):
            # Создаем мок StreamingResponse
            streaming_response = Mock(spec=StreamingResponse)
            mock_dependencies['content_processor'].process_content = AsyncMock(return_value=streaming_response)

            # Act
            result = await request_handler._handle_direct_request(path, "GET", None, {}, {})

        # Assert
        assert result == (streaming_response, 200, '')

    @pytest.mark.asyncio
    async def test_handle_direct_request_unknown_result(self, request_handler, mock_dependencies):
        """Тест обработки неизвестного результата в прямом запросе"""
        # Arrange
        path = "https://example.com/data"

        # Мокируем утилиты
        with patch('src.services.request_handler.build_url', return_value="https://example.com/data"):
            # Мокируем процессор контента возвращающий неизвестный тип
            mock_dependencies['content_processor'].process_content = AsyncMock(return_value="unknown")

            # Act
            result = await request_handler._handle_direct_request(path, "GET", None, {}, {})

        # Assert
        assert result == ("unknown", 500, 'application/octet-stream')

    @pytest.mark.asyncio
    async def test_handle_request_with_post_data_and_params(self, request_handler):
        """Тест обработки запроса с POST данными и параметрами"""
        # Arrange
        path = "direct/path"
        method = "POST"
        post_data = {"key": "value"}
        query_params = {"query": "param"}
        request_headers = {"Content-Type": "application/json"}

        request_handler._handle_direct_request = AsyncMock(return_value=({"status": "ok"}, 200, "application/json"))

        # Act
        result = await request_handler.handle_request(path, method, post_data, query_params, request_headers)

        # Assert
        assert result == ({"status": "ok"}, 200, "application/json")
        request_handler._handle_direct_request.assert_called_once_with(
            path, method, post_data, query_params, request_headers
        )

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc2_param_decoding_error(self, request_handler, mock_dependencies):
        """Тест обработки ошибки декодирования параметров в enc2"""
        # Arrange
        segments = ["enc2", "encoded_data", "invalid_param"]

        # Мокируем утилиты
        with patch('src.services.request_handler.decode_base64_url') as mock_decode:
            mock_decode.side_effect = [
                "decoded_main",  # Первый вызов успешен
                Exception("Decoding error")  # Второй вызов падает
            ]

            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, ["url"])):
                with patch('src.services.request_handler.build_url', return_value="https://target.com"):
                    # Мокируем процессор контента
                    proxy_response = ProxyResponse(
                        status=200,
                        body=b'response',
                        headers={"content-type": "text/plain"}
                    )
                    mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

                    # Act
                    result = await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

        # Assert - должен продолжить выполнение несмотря на ошибку
        assert result[1] == 200

    @pytest.mark.asyncio
    async def test_handle_encoded_request_enc2_param_without_value(self, request_handler, mock_dependencies):
        """Тест обработки параметра без значения в enc2"""
        # Arrange
        segments = ["enc2", "encoded_data", "param_without_value"]

        # Мокируем утилиты
        with patch('src.services.request_handler.decode_base64_url') as mock_decode:
            mock_decode.side_effect = [
                "decoded_main",
                "key_without_value"  # Параметр без знака =
            ]

            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, ["url"])):
                with patch('src.services.request_handler.build_url', return_value="https://target.com"):
                    # Мокируем процессор контента
                    proxy_response = ProxyResponse(
                        status=200,
                        body=b'response',
                        headers={"content-type": "text/plain"}
                    )
                    mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

                    # Act
                    await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

        # Assert - параметр без значения должен быть добавлен как ключ с None

    @pytest.mark.asyncio
    async def test_handle_encoded_request_logging(self, request_handler, mock_dependencies, caplog):
        """Тест логирования в обработке закодированных запросов"""
        # Arrange
        segments = ["enc", "encoded_data", "segment1"]

        # Мокируем утилиты
        with patch('src.services.request_handler.decode_base64_url', return_value="decoded_data"):
            with patch('src.services.request_handler.parse_encoded_data', return_value=({}, [])):
                with patch('src.services.request_handler.build_url', return_value="https://target.com"):
                    # Мокируем процессор контента
                    proxy_response = ProxyResponse(
                        status=200,
                        body=b'response',
                        headers={"content-type": "text/plain"}
                    )
                    mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

                    # Act
                    with caplog.at_level('INFO'):
                        await request_handler._handle_encoded_request(segments, "GET", None, {}, {})

        # Assert
        assert "Processing encoded GET request with 3 segments" in caplog.text
        assert "Decoded data: decoded_data from encoded: enc" in caplog.text
        assert "Proxying GET with encode type enc request to: https://target.com" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_direct_request_logging(self, request_handler, mock_dependencies, caplog):
        """Тест логирования в обработке прямых запросов"""
        # Arrange
        path = "https://example.com/data"

        # Мокируем утилиты
        with patch('src.services.request_handler.build_url', return_value="https://example.com/data"):
            # Мокируем процессор контента
            proxy_response = ProxyResponse(
                status=200,
                body=b'response',
                headers={"content-type": "text/plain"}
            )
            mock_dependencies['content_processor'].process_content = AsyncMock(return_value=proxy_response)

            # Act
            with caplog.at_level('INFO'):
                await request_handler._handle_direct_request(path, "GET", None, {}, {})

        # Assert
        assert "Proxying GET request to: https://example.com/data" in caplog.text