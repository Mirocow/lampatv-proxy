#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import json
import logging
import urllib.parse
from flask import Flask, request, jsonify, Response
import requests
import re

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('lampa-jsonp-proxy')

app = Flask(__name__)

# Конфигурация
CONFIG = {
    'timeout': 30,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'log_enabled': True,
    'allowed_domains': []  # Добавьте разрешенные домены для защиты от SSRF
}

def log_message(message):
    """Логирование сообщений"""
    if CONFIG['log_enabled']:
        logger.info(message)

def validate_callback_name(callback):
    """Проверка безопасности имени callback функции"""
    if not re.match(r'^[a-zA-Z_$][0-9a-zA-Z_$]*$', callback):
        return 'callback'
    return callback

def is_allowed_url(url):
    """Проверка URL на допустимость (базовая защита от SSRF)"""
    if not CONFIG['allowed_domains']:
        return True  # Если список пуст, разрешаем все
        
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.lower()
    
    for allowed_domain in CONFIG['allowed_domains']:
        if domain.endswith(allowed_domain.lower()):
            return True
    return False

def decode_encoded_part(encoded):
    """Декодирование закодированной части URL"""
    try:
        decoded_url = urllib.parse.unquote(encoded)
        decoded_bytes = base64.b64decode(decoded_url)
        return decoded_bytes.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Failed to decode: {str(e)}")

def parse_params_from_path(segments):
    """Извлечение параметров из пути"""
    params = {}
    remaining_segments = []
    
    i = 0
    while i < len(segments):
        if segments[i] == 'param' and i + 1 < len(segments):
            param_parts = segments[i + 1].split('=', 1)
            if len(param_parts) == 2:
                key = urllib.parse.unquote(param_parts[0])
                value = urllib.parse.unquote(param_parts[1])
                params[key] = value
            i += 2
        else:
            remaining_segments.append(segments[i])
            i += 1
    
    return params, remaining_segments

def build_target_url(segments):
    """Построение целевого URL из сегментов"""
    for i, segment in enumerate(segments):
        if segment.startswith('http'):
            full_url = '/'.join(segments[i:])
            if '://' not in full_url:
                full_url = 'https://' + full_url
            
            # Проверка безопасности URL
            if not is_allowed_url(full_url):
                raise ValueError(f"URL domain not allowed: {full_url}")
                
            return full_url
    raise ValueError("No valid URL found in path")

def normalize_headers(headers):
    """Нормализация заголовков для JSON"""
    normalized = {}
    for key, value in headers.items():
        # Сохраняем set-cookie как массив
        if key.lower() == 'set-cookie':
            if isinstance(value, list):
                normalized[key.lower()] = value
            else:
                normalized[key.lower()] = [value]
        else:
            normalized[key.lower()] = [value] if not isinstance(value, list) else value
    return normalized

def make_jsonp_request(target_url, method='GET', headers=None, data=None, callback='callback'):
    """Выполнение HTTP запроса с возвратом в формате JSONP"""
    log_message(f"Making JSONP request to: {method} {target_url}")
    
    request_headers = {
        'User-Agent': CONFIG['user_agent']
    }
    
    # Добавляем кастомные заголовки
    if headers:
        for key, value in headers.items():
            if key.lower() == 'user-agent':
                request_headers['User-Agent'] = value
            elif key.lower() == 'cookie':
                request_headers['Cookie'] = value
            else:
                request_headers[key] = value
    
    try:
        # Безопасные параметры запроса
        request_params = {
            'headers': request_headers,
            'timeout': CONFIG['timeout'],
            'verify': True  # ВКЛЮЧЕНА проверка SSL сертификатов
        }
        
        if data:
            request_params['data'] = data
            
        if method.upper() == 'POST':
            response = requests.post(target_url, **request_params)
        else:
            response = requests.get(target_url, **request_params)
        
        # Нормализуем заголовки ответа
        normalized_headers = normalize_headers(dict(response.headers))
        
        log_message(f"Response status: {response.status_code}")
        
        # Формируем JSONP ответ
        response_data = {
            'body': response.text,
            'headers': normalized_headers,
            'status': response.status_code
        }
        
        # Оборачиваем в JSONP callback с проверкой безопасности
        safe_callback = validate_callback_name(callback)
        jsonp_response = f"{safe_callback}({json.dumps(response_data, ensure_ascii=False)})"
        return jsonp_response
        
    except requests.exceptions.Timeout:
        error_msg = "Request timeout"
        log_message(f"Request failed: {error_msg}")
    except requests.exceptions.SSLError as e:
        error_msg = f"SSL error: {str(e)}"
        log_message(f"Request failed: {error_msg}")
    except requests.exceptions.ConnectionError:
        error_msg = "Connection error"
        log_message(f"Request failed: {error_msg}")
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        log_message(f"Request failed: {error_msg}")
    
    # Возвращаем ошибку в формате JSONP
    safe_callback = validate_callback_name(callback)
    error_response = {
        'error': "An internal error occurred while processing the request",
        'body': '',
        'headers': {},
        'status': 500
    }
    return f"{safe_callback}({json.dumps(error_response, ensure_ascii=False)})"

def handle_jsonp_request(path, method, data, callback):
    """Обработка JSONP запросов различных типов"""
    segments = [segment for segment in path.strip('/').split('/') if segment]
    
    if not segments:
        safe_callback = validate_callback_name(callback)
        return f"{safe_callback}({json.dumps({'error': 'Empty request path'}, ensure_ascii=False)})"
    
    # Обработка различных типов кодирования
    if segments[0] in ['enc', 'enc1', 'enc2']:
        if len(segments) < 2:
            safe_callback = validate_callback_name(callback)
            return f"{safe_callback}({json.dumps({'error': 'Invalid encoded request'}, ensure_ascii=False)})"
        
        encoding_type = segments[0]
        encoded_part = segments[1]
        remaining_path = '/'.join(segments[2:])
        
        try:
            decoded_base = decode_encoded_part(encoded_part)
            log_message(f"Decoded base ({encoding_type}): {decoded_base}")
            
            # Парсим параметры из декодированной базы
            params, path_segments = parse_params_from_path(
                [s for s in decoded_base.strip('/').split('/') if s]
            )
            
            # Строим целевой URL
            target_url = build_target_url(path_segments)
            
            # Добавляем оставшийся путь
            if remaining_path:
                target_url = target_url.rstrip('/') + '/' + remaining_path
                
            return make_jsonp_request(target_url, method, params, data, callback)
            
        except Exception as e:
            safe_callback = validate_callback_name(callback)
            return f"{safe_callback}({json.dumps({'error': str(e)}, ensure_ascii=False)})"
    
    # Обработка запросов с параметрами
    elif segments[0] == 'param':
        try:
            params, remaining_segments = parse_params_from_path(segments[1:])
            target_url = build_target_url(remaining_segments)
            return make_jsonp_request(target_url, method, params, data, callback)
        except Exception as e:
            safe_callback = validate_callback_name(callback)
            return f"{safe_callback}({json.dumps({'error': str(e)}, ensure_ascii=False)})"
    
    # Обработка cookie_plus запросов
    elif segments[0] == 'cookie_plus':
        try:
            params = {}
            target_url = None
            
            i = 1  # Пропускаем 'cookie_plus'
            while i < len(segments):
                if (i + 2 < len(segments) and 
                    segments[i] == 'param' and 
                    segments[i + 1].startswith('Cookie=')):
                    
                    cookie_value = segments[i + 1][7:]  # Убираем 'Cookie='
                    params['Cookie'] = urllib.parse.unquote(cookie_value)
                    i += 2
                elif segments[i] == 'param' and i + 1 < len(segments):
                    param_parts = segments[i + 1].split('=', 1)
                    if len(param_parts) == 2:
                        key = urllib.parse.unquote(param_parts[0])
                        value = urllib.parse.unquote(param_parts[1])
                        params[key] = value
                    i += 2
                elif segments[i].startswith('http'):
                    target_url = '/'.join(segments[i:])
                    break
                else:
                    i += 1
            
            if not target_url:
                safe_callback = validate_callback_name(callback)
                return f"{safe_callback}({json.dumps({'error': 'No target URL found'}, ensure_ascii=False)})"
            
            return make_jsonp_request(target_url, method, params, data, callback)
            
        except Exception as e:
            safe_callback = validate_callback_name(callback)
            return f"{safe_callback}({json.dumps({'error': str(e)}, ensure_ascii=False)})"
    
    # Прямой URL
    else:
        try:
            target_url = build_target_url(segments)
            return make_jsonp_request(target_url, method, None, data, callback)
        except Exception as e:
            safe_callback = validate_callback_name(callback)
            return f"{safe_callback}({json.dumps({'error': str(e)}, ensure_ascii=False)})"

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def jsonp_proxy_handler(path):
    """Основной обработчик JSONP запросов"""
    log_message(f"Incoming JSONP request: {request.method} /{path}")
    
    # Получаем callback функцию из параметров с проверкой безопасности
    callback = validate_callback_name(request.args.get('callback', 'callback'))
    
    # Получаем данные тела для POST запросов
    post_data = None
    if request.method == 'POST':
        post_data = request.get_data(as_text=True)
    
    # Обрабатываем JSONP запрос
    response = handle_jsonp_request(path, request.method, post_data, callback)
    
    # Возвращаем как JavaScript
    return Response(
        response=response,
        status=200,
        mimetype='application/javascript',
        headers={
            'Access-Control-Allow-Origin': '*',
            'X-Content-Type-Options': 'nosniff'
        }
    )

@app.errorhandler(404)
def not_found(error):
    callback = validate_callback_name(request.args.get('callback', 'callback'))
    return Response(
        response=f"{callback}({json.dumps({'error': 'Endpoint not found'}, ensure_ascii=False)})",
        status=200,
        mimetype='application/javascript'
    )

@app.errorhandler(500)
def internal_error(error):
    callback = validate_callback_name(request.args.get('callback', 'callback'))
    return Response(
        response=f"{callback}({json.dumps({'error': 'Internal server error'}, ensure_ascii=False)})",
        status=200,
        mimetype='application/javascript'
    )

if __name__ == '__main__':
    log_message("Starting Lampa JSONP proxy server on http://0.0.0.0:8080")
    
    # ВАЖНО: Не отключаем предупреждения о SSL в продакшене
    # import warnings
    # warnings.filterwarnings('ignore', message='Unverified HTTPS request')
    
    app.run(host='0.0.0.0', port=8080, debug=False)
