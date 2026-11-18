import json
from urllib.parse import urlparse
import httpx
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

HOP_BY_HOP_HEADERS = {
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailers',
    'transfer-encoding',
    'upgrade',
    'content-encoding',
    'content-length',
    'host',
}

@csrf_exempt
def proxy_view(request):
    """
    Dynamic API Proxy endpoint.
    Accepts target URL via query param (?url=...) or JSON request body {"url": "..."}.
    Forwards request to the destination URL and returns the upstream response
    preserving status code, content-type, and dynamic/unstructured payload.
    """
    target_url = request.GET.get('url')
    method = request.method
    headers = {}
    params = {}
    data = None
    json_data = None

    # Check if request has JSON payload with config/data
    if request.content_type == 'application/json' and request.body:
        try:
            body_json = json.loads(request.body.decode('utf-8'))
            if isinstance(body_json, dict):
                # If 'url' is provided in JSON body
                if not target_url and 'url' in body_json:
                    target_url = body_json.get('url')
                
                # Check for wrapped schema: {"url": "...", "method": "...", "headers": {}, "params": {}, "data": ...}
                if 'method' in body_json:
                    method = str(body_json['method']).upper()
                if 'headers' in body_json and isinstance(body_json['headers'], dict):
                    headers.update(body_json['headers'])
                if 'params' in body_json and isinstance(body_json['params'], dict):
                    params.update(body_json['params'])
                
                if 'json' in body_json:
                    json_data = body_json['json']
                elif 'data' in body_json:
                    if isinstance(body_json['data'], (dict, list)):
                        json_data = body_json['data']
                    else:
                        data = str(body_json['data']).encode('utf-8')
                elif 'url' in body_json and len(body_json) == 1:
                    # Only {"url": "..."} was provided
                    pass
                elif 'url' not in body_json:
                    # Treat entire body as payload to forward
                    json_data = body_json
            else:
                json_data = body_json
        except json.JSONDecodeError:
            data = request.body
    elif request.body:
        data = request.body

    # Fallback to POST form data if url is there
    if not target_url and request.POST.get('url'):
        target_url = request.POST.get('url')

    if not target_url:
        return JsonResponse(
            {
                'error': 'Target URL is required.',
                'usage': {
                    'query_param': '/api/proxy/?url=https://api.example.com/data',
                    'json_body': {
                        'url': 'https://api.example.com/data',
                        'method': 'GET or POST (optional)',
                        'headers': {'Custom-Header': 'value (optional)'},
                        'params': {'key': 'value (optional)'},
                        'data': 'payload (optional)'
                    }
                }
            },
            status=400
        )

    # Validate URL structure
    parsed_url = urlparse(target_url)
    if not parsed_url.scheme or parsed_url.scheme not in ('http', 'https') or not parsed_url.netloc:
        return JsonResponse(
            {'error': f'Invalid URL scheme "{parsed_url.scheme}". Only HTTP and HTTPS are supported.'},
            status=400
        )

    # Forward any non-hop-by-hop headers from client if not already overridden
    for k, v in request.headers.items():
        k_lower = k.lower()
        if k_lower not in HOP_BY_HOP_HEADERS and k not in headers:
            headers[k] = v

    try:
        # Perform upstream request
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            upstream_response = client.request(
                method=method,
                url=target_url,
                params=params if params else None,
                headers=headers,
                content=data if json_data is None else None,
                json=json_data,
            )

        # Build downstream response
        content_type = upstream_response.headers.get('content-type', 'application/json')
        response = HttpResponse(
            content=upstream_response.content,
            status=upstream_response.status_code,
            content_type=content_type,
        )

        # Forward non-hop-by-hop response headers
        for key, val in upstream_response.headers.items():
            if key.lower() not in HOP_BY_HOP_HEADERS:
                response[key] = val

        return response

    except httpx.TimeoutException as exc:
        return JsonResponse(
            {'error': 'Upstream request timed out.', 'details': str(exc)},
            status=504
        )
    except httpx.RequestError as exc:
        return JsonResponse(
            {'error': 'Failed to reach upstream server.', 'details': str(exc)},
            status=502
        )
    except Exception as exc:
        return JsonResponse(
            {'error': 'Proxy internal server error.', 'details': str(exc)},
            status=500
        )

# Backward-compatibility alias
gateway_view = proxy_view
