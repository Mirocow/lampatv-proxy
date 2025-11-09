import re
import urllib.parse
import base64
import json
from typing import Dict, List, Tuple, Any, Optional


URL_PATTERN = re.compile(r'(https?://[^\s]+)', flags=re.IGNORECASE)
REPLACE_WRONG_SLASHES_PATTERN = re.compile(r"(https?:/)([^/])", flags=re.IGNORECASE)
RANGE_MATCH_PATTERN= re.compile(r'bytes=(\d+)-(\d*)', flags=re.IGNORECASE)
FULL_RANGE_MATCH_PATTERN= re.compile(r'bytes\s+\*?/?(\d+)-?(\d+)?/(\d+)', flags=re.IGNORECASE)


def decode_base64_url(encoded_str: str) -> str:
    """Декодирование base64 URL с обработкой ошибок"""
    try:
        decoded_url = urllib.parse.unquote(encoded_str)

        # Заменяем URL-safe символы обратно
        decoded_url = decoded_url.replace('-', '+').replace('_', '/')

        # Добавляем padding если необходимо
        missing_padding = len(decoded_url) % 4
        if missing_padding:
            decoded_url += '=' * (4 - missing_padding)

        result = base64.b64decode(decoded_url).decode('utf-8')

        return result

    except base64.binascii.Error as e:
        raise ValueError(f"Invalid base64 string: {str(e)}")

    except UnicodeDecodeError as e:
        raise ValueError(f"Invalid UTF-8 in decoded string: {str(e)}")

    except Exception as e:
        raise ValueError(f"Unexpected error during decoding: {str(e)}")


def encode_base64_url(original_str: str) -> str:
    """Кодирование строки в base64 URL-safe формат"""
    try:
        # Преобразуем строку в байты
        original_bytes = original_str.encode('utf-8')

        # Кодируем в base64
        base64_bytes = base64.b64encode(original_bytes)
        base64_str = base64_bytes.decode('utf-8')

        # Делаем URL-safe: заменяем + на - и / на _
        url_safe_str = base64_str.replace('+', '-').replace('/', '_')

        # Убираем padding (=)
        url_safe_str = url_safe_str.rstrip('=')

        return url_safe_str

    except Exception as e:
        raise ValueError(f"Base64 encoding error: {str(e)}")


def normalize_url(url: str) -> str:
    """Нормализация URL и исправление проблем с протоколом"""
    if not url:
        raise ValueError("Empty URL")

    # Убираем дублирующиеся протоколы
    protocols = ['https://', 'http://']
    for proto1 in protocols:
        for proto2 in protocols:
            duplicate = proto1 + proto2
            if url.startswith(duplicate):
                url = url[len(proto1):]
                break

    # Обрабатываем protocol-relative URLs (начинающиеся с //)
    if url.startswith('//'):
        url = 'https:' + url

    # Исправляем неправильные слеши
    url = REPLACE_WRONG_SLASHES_PATTERN.sub(r'\1/\2', url)

    # Добавляем протокол если отсутствует
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    return url


def parse_encoded_data(encoded_str: str) -> Tuple[Dict[str, str], List[str]]:
    """Парсинг закодированных данных в формате prox_enc"""
    params = {}
    url = []

    if not encoded_str:
        return params, url

    # Разделяем строку по символу '/'
    parts = encoded_str.split('/')

    i = 0
    n = 0

    # Обрабатываем части последовательно
    while i < len(parts):
        # Если находим "param", то следующий элемент должен быть в формате "ключ=значение"
        if parts[i] == 'param' and i + 1 < len(parts):
            key_value = parts[i + 1]
            if '=' in key_value:
                key, value = key_value.split('=', 1)
                # Декодируем URL-encoded значение
                decoded_value = urllib.parse.unquote(value)
                params[key] = decoded_value
                i += 2  # Пропускаем два элемента: 'param' и 'ключ=значение'
                n = i
                continue

        i += 1

    return params, parts[n:]


def build_url(segments: List[str], query_params: Optional[Dict] = None) -> str:
    """Построение целевого URL из сегментов с возможностью добавления query-параметров"""
    if not segments:
        raise ValueError("No URL segments provided")

    url = '/'.join(segments)

    url_match = URL_PATTERN.search(url)
    if url_match:
        url = url_match.group(1)
    else:
        url = normalize_url(url)

    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"Invalid hostname in URL: {url}")

    # Добавляем query-параметры если они переданы
    if query_params:
        # Если query_params передан как список кортежей
        if isinstance(query_params, list) and all(isinstance(item, (list, tuple)) for item in query_params):
            query_string = urllib.parse.urlencode(query_params)
        # Если query_params передан как словарь
        elif isinstance(query_params, dict):
            query_string = urllib.parse.urlencode(query_params)
        else:
            raise ValueError("query_params must be a dictionary or list of tuples")

        # Объединяем существующие query-параметры с новыми
        current_query = parsed.query
        if current_query:
            new_query = f"{current_query}&{query_string}"
        else:
            new_query = query_string

        # Собираем URL с новыми параметрами
        parsed = parsed._replace(query=new_query)
        url = urllib.parse.urlunparse(parsed)

    return url


def is_valid_json(text: str) -> bool:
    """Проверка валидности JSON включая примитивы"""
    if not text:
        return False

    text = text.strip()
    if not text:
        return False

    # Стандартная проверка JSON
    if (text.startswith('{') and text.endswith('}')) or (text.startswith('[') and text.endswith(']')):
        try:
            json.loads(text)
            return True
        except (json.JSONDecodeError, ValueError):
            return False

    return False


def parse_range_header(range_header: Optional[str], file_size: int) -> Tuple[int, int]:
    """Парсит заголовок Range и возвращает начальный и конечный байты"""
    if not range_header:
        return 0, file_size - 1 if file_size > 0 else 0

    try:
        # Формат: bytes=start-end
        range_match = RANGE_MATCH_PATTERN.match(range_header)
        if not range_match:
            return 0, file_size - 1 if file_size > 0 else 0

        start = int(range_match.group(1))
        end_str = range_match.group(2)

        if end_str:
            end = int(end_str)
        else:
            # Если конец не указан, используем до конца файла
            end = file_size - 1 if file_size > 0 else 0

        # Валидация диапазона
        if file_size > 0:
            if start < 0:
                start = 0
            if start >= file_size:
                # Если начало после конца файла, возвращаем пустой диапазон
                start = file_size - 1
                end = file_size - 1
            if end >= file_size:
                end = file_size - 1
            if start > end:
                start, end = end, start  # Корректируем если начало после конца

        return start, end

    except Exception as e:
        return 0, file_size - 1 if file_size > 0 else 0
