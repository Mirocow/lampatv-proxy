#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import base64
import json
import logging
import urllib.parse
import traceback
from flask import Flask, request, jsonify, Response
import requests
import re

# ==================== Configuration & Setup ====================

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('lampa-jsonp-proxy')

app = Flask(__name__)

# Configuration dictionary
CONFIG = {
    'timeout': 30,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'log_enabled': True,
    'allowed_domains': []  # Add domains to restrict access if needed
}

# ==================== Utility Functions ====================


def log_message(message):
    """Log an informational message."""
    if CONFIG['log_enabled']:
        logger.info(message)


def log_debug(message):
    """Log a debug message."""
    if CONFIG['log_enabled']:
        logger.debug(message)


def log_error(message):
    """Log an error message with traceback."""
    if CONFIG['log_enabled']:
        logger.error(f"{message}\nTraceback:\n{traceback.format_exc()}")


def validate_callback_name(callback):
    """Validate and sanitize the JSONP callback function name."""
    if not re.match(r'^[a-zA-Z_$][0-9a-zA-Z_$]*$', callback):
        return 'callback'
    return callback


def is_allowed_url(url):
    """Check if the URL belongs to an allowed domain."""
    if not CONFIG['allowed_domains']:
        return True

    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()

        for allowed_domain in CONFIG['allowed_domains']:
            if domain.endswith(allowed_domain.lower()):
                return True
        return False
    except Exception as e:
        log_error(f"Error in is_allowed_url for URL: {url}")
        return False


def decode_encoded_part(encoded):
    """Decode a base64 and URL-encoded string."""
    try:
        log_debug(f"Attempting to decode: {encoded}")
        decoded_url = urllib.parse.unquote(encoded)
        decoded_bytes = base64.b64decode(decoded_url)
        result = decoded_bytes.decode('utf-8')
        log_debug(f"Successfully decoded to: {result}")
        return result
    except Exception as e:
        log_error(f"Failed to decode: {encoded}")
        raise ValueError(f"Failed to decode: {str(e)}")


def parse_params_from_path(segments):
    """Parse parameters from path segments and return parameters and remaining segments."""
    params = {}
    remaining_segments = []
    url_start_index = -1

    log_debug(f"Parsing parameters from segments: {segments}")

    # Find where the actual URL starts
    for i, segment in enumerate(segments):
        if segment.startswith(('http://', 'https://')):
            url_start_index = i
            break
        # Also check for segments that might be part of a URL
        elif '://' in segment:
            url_start_index = i
            break

    # If no URL protocol found, look for segments that contain dots (likely domains)
    if url_start_index == -1:
        for i, segment in enumerate(segments):
            if '.' in segment and not '=' in segment:
                url_start_index = i
                break

    # Parse parameters only before the URL starts
    if url_start_index != -1:
        i = 0
        while i < url_start_index:
            if segments[i] == 'param' and i + 1 < url_start_index:
                param_parts = segments[i + 1].split('=', 1)
                if len(param_parts) == 2:
                    key = urllib.parse.unquote(param_parts[0])
                    value = urllib.parse.unquote(param_parts[1])
                    params[key] = value
                    log_debug(f"Found parameter: {key} = {value}")
                i += 2
            else:
                i += 1

        # All segments from url_start_index onward are part of the URL
        remaining_segments = segments[url_start_index:]
    else:
        # If no clear URL found, use all segments as URL
        remaining_segments = segments

    log_debug(
        f"Parsed params: {params}, remaining segments: {remaining_segments}")
    return params, remaining_segments

def build_target_url_from_segments(segments):
    """Construct the target URL from path segments."""
    log_debug(f"Building target URL from segments: {segments}")

    if not segments:
        raise ValueError("No URL segments provided")

    # Если сегмент уже содержит полный URL с протоколом, используем как есть
    if len(segments) == 1 and '://' in segments[0]:
        target_url = segments[0]
        log_debug(f"Using full URL with protocol: {target_url}")
        return target_url

    # Join segments to form the path
    full_path = '/'.join(segments)
    log_debug(f"Full path: {full_path}")

    # Если путь уже содержит протокол, используем как есть
    if full_path.startswith(('http://', 'https://')):
        target_url = full_path
    else:
        # Иначе добавляем https://
        target_url = 'https://' + full_path

    # Исправляем двойные слеши в URL
    target_url = re.sub(r'(https?:/)([^/])', r'\1/\2', target_url)

    log_debug(f"Final target URL: {target_url}")
    return target_url


def normalize_headers(headers):
    """Normalize response headers for JSON serialization."""
    normalized = {}
    for key, value in headers.items():
        if key.lower() == 'set-cookie':
            if isinstance(value, list):
                normalized[key.lower()] = value
            else:
                normalized[key.lower()] = [value]
        else:
            normalized[key.lower()] = [value] if not isinstance(
                value, list) else value
    return normalized


def make_jsonp_request(target_url, method='GET', params=None, data=None, callback='callback'):
    """Make the actual HTTP request and return a JSONP response."""
    log_message(f"Making JSONP request to: {method} {target_url}")

    # Убедимся, что URL не содержит двойного протокола
    if target_url.startswith('https://https://') or target_url.startswith('http://https://') or target_url.startswith('https://http://'):
        # Удаляем лишний протокол
        if target_url.startswith('https://https://'):
            target_url = 'https://' + target_url[8:]
        elif target_url.startswith('http://https://'):
            target_url = 'https://' + target_url[7:]
        elif target_url.startswith('https://http://'):
            target_url = 'http://' + target_url[8:]
        log_debug(f"Fixed double protocol URL: {target_url}")

    # Ensure URL has a valid scheme
    parsed_url = urllib.parse.urlparse(target_url)
    if not parsed_url.scheme:
        target_url = 'https://' + target_url
        log_debug(f"Added scheme to URL: {target_url}")

    # Validate hostname
    parsed_url = urllib.parse.urlparse(target_url)
    if not parsed_url.hostname or parsed_url.hostname in ['http', 'https']:
        raise ValueError(f"Invalid hostname in URL: {target_url}")

    # Prepare request headers
    request_headers = {'User-Agent': CONFIG['user_agent']}

    # Add parameters to URL for GET requests
    if params and method.upper() == 'GET':
        # Parse existing URL to preserve any existing query parameters
        url_parts = list(urllib.parse.urlparse(target_url))
        query_dict = urllib.parse.parse_qs(url_parts[4])

        # Add new parameters
        for key, value in params.items():
            query_dict[key] = [value]

        # Rebuild query string
        url_parts[4] = urllib.parse.urlencode(query_dict, doseq=True)
        target_url = urllib.parse.urlunparse(url_parts)
        log_debug(f"URL with parameters: {target_url}")

    try:
        # Configure request parameters
        request_params = {
            'headers': request_headers,
            'timeout': CONFIG['timeout'],
            'verify': True
        }

        if data and method.upper() == 'POST':
            request_params['data'] = data

        log_debug(f"Request parameters: {request_params}")

        # Make the HTTP request
        if method.upper() == 'POST':
            response = requests.post(target_url, **request_params)
        else:
            response = requests.get(target_url, **request_params)

        log_debug(f"Received response with status: {response.status_code}")

        # Prepare response data
        normalized_headers = normalize_headers(dict(response.headers))
        response_data = {
            'body': response.text,
            'headers': normalized_headers,
            'status': response.status_code
        }

        # Create JSONP response
        safe_callback = validate_callback_name(callback)
        jsonp_response = f"{safe_callback}({json.dumps(response_data, ensure_ascii=False)})"

        return jsonp_response

    except requests.exceptions.Timeout:
        error_msg = "Request timeout"
        log_error(f"Request timeout to {target_url}")
    except requests.exceptions.SSLError as e:
        error_msg = f"SSL error: {str(e)}"
        log_error(f"SSL error to {target_url}")
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Connection error: {str(e)}"
        log_error(f"Connection error to {target_url}")
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)}"
        log_error(f"Request exception to {target_url}")
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        log_error(f"Unexpected error during request to {target_url}")

    # Return error response
    safe_callback = validate_callback_name(callback)
    error_response = {
        'error': error_msg,
        'body': '',
        'headers': {},
        'status': 500
    }
    return f"{safe_callback}({json.dumps(error_response, ensure_ascii=False)})"

# ==================== Request Handler ====================


def handle_jsonp_request(path, method, data, callback):
    """Main handler for JSONP requests."""
    log_debug(f"Handling JSONP request - Path: '{path}', Method: {method}")

    segments = [segment for segment in path.strip('/').split('/') if segment]
    log_debug(f"Path segments: {segments}")

    if not segments:
        safe_callback = validate_callback_name(callback)
        return f"{safe_callback}({json.dumps({'error': 'Empty request path'}, ensure_ascii=False)})"

    # Handle encoded requests (enc, enc1, enc2)
    if segments[0] in ['enc', 'enc1', 'enc2']:
        if len(segments) < 2:
            safe_callback = validate_callback_name(callback)
            return f"{safe_callback}({json.dumps({'error': 'Invalid encoded request'}, ensure_ascii=False)})"

        encoding_type = segments[0]
        encoded_part = segments[1]
        remaining_segments = segments[2:]

        try:
            decoded_base = decode_encoded_part(encoded_part)
            decoded_segments = [
                s for s in decoded_base.strip('/').split('/') if s]

            params, path_segments = parse_params_from_path(decoded_segments)
            target_url = build_target_url_from_segments(path_segments)

            if remaining_segments:
                target_url = target_url.rstrip(
                    '/') + '/' + '/'.join(remaining_segments)

            return make_jsonp_request(target_url, method, params, data, callback)

        except Exception as e:
            safe_callback = validate_callback_name(callback)
            return f"{safe_callback}({json.dumps({'error': str(e)}, ensure_ascii=False)})"

    # Handle parameter-based requests - ИСПРАВЛЕННАЯ ЛОГИКА
    elif segments[0] == 'param':
        try:
            params, remaining_segments = parse_params_from_path(segments[1:])

            if not remaining_segments:
                raise ValueError("No target URL provided after parameters")

            log_debug(f"Parameters extracted: {params}")
            log_debug(f"Remaining segments for URL: {remaining_segments}")

            target_url = build_target_url_from_segments(remaining_segments)
            return make_jsonp_request(target_url, method, params, data, callback)

        except Exception as e:
            log_error(f"Error processing param request: {str(e)}")
            safe_callback = validate_callback_name(callback)
            return f"{safe_callback}({json.dumps({'error': str(e)}, ensure_ascii=False)})"

    # Handle cookie_plus requests
    elif segments[0] == 'cookie_plus':
        try:
            params = {}
            target_url = None
            url_found = False

            i = 1
            while i < len(segments):
                if (i + 1 < len(segments) and
                    segments[i] == 'param' and
                        segments[i + 1].startswith('Cookie=')):

                    cookie_value = segments[i + 1][7:]  # Remove 'Cookie='
                    params['Cookie'] = urllib.parse.unquote(cookie_value)
                    i += 2
                elif segments[i] == 'param' and i + 1 < len(segments):
                    param_parts = segments[i + 1].split('=', 1)
                    if len(param_parts) == 2:
                        key = urllib.parse.unquote(param_parts[0])
                        value = urllib.parse.unquote(param_parts[1])
                        params[key] = value
                    i += 2
                elif '://' in segments[i]:
                    # Нашли URL, берем все оставшиеся сегменты
                    target_url = '/'.join(segments[i:])
                    url_found = True
                    break
                else:
                    i += 1

            if not url_found:
                safe_callback = validate_callback_name(callback)
                return f"{safe_callback}({json.dumps({'error': 'No target URL found'}, ensure_ascii=False)})"

            return make_jsonp_request(target_url, method, params, data, callback)

        except Exception as e:
            safe_callback = validate_callback_name(callback)
            return f"{safe_callback}({json.dumps({'error': str(e)}, ensure_ascii=False)})"

    # Handle direct URL requests
    else:
        log_debug("Processing direct URL request")
        try:
            # Use the entire path as the URL
            target_url = path

            # Add scheme if missing
            if not target_url.startswith(('http://', 'https://')):
                target_url = 'https://' + target_url

            log_debug(f"Final URL for request: {target_url}")

            # Validate the URL
            parsed = urllib.parse.urlparse(target_url)
            if not parsed.netloc:
                raise ValueError(f"Invalid URL - no hostname: {target_url}")

            return make_jsonp_request(target_url, method, None, data, callback)

        except Exception as e:
            log_error(f"Error processing direct URL: {path}")
            safe_callback = validate_callback_name(callback)
            return f"{safe_callback}({json.dumps({'error': str(e)}, ensure_ascii=False)})"

# ==================== Flask Routes ====================


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def jsonp_proxy_handler(path):
    """Main Flask route handler for all requests."""
    log_message(f"Incoming JSONP request: {request.method} /{path}")

    callback = validate_callback_name(request.args.get('callback', 'callback'))

    post_data = None
    if request.method == 'POST':
        post_data = request.get_data(as_text=True)

    response = handle_jsonp_request(path, request.method, post_data, callback)

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
    """Handle 404 errors."""
    callback = validate_callback_name(request.args.get('callback', 'callback'))
    return Response(
        response=f"{callback}({json.dumps({'error': 'Endpoint not found'}, ensure_ascii=False)})",
        status=200,
        mimetype='application/javascript'
    )


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    callback = validate_callback_name(request.args.get('callback', 'callback'))
    return Response(
        response=f"{callback}({json.dumps({'error': 'Internal server error'}, ensure_ascii=False)})",
        status=200,
        mimetype='application/javascript'
    )

# ==================== Application Entry Point ====================


if __name__ == '__main__':
    log_message("Starting Lampa JSONP proxy server on http://0.0.0.0:8080")
    app.run(host='0.0.0.0', port=8080, debug=False)
