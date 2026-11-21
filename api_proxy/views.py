import httpx
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Endpoint, normalize_path

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

# Not forwarded upstream: httpx advertises only the encodings it can decode.
# Passing the client's (e.g. "gzip, deflate, br") through can get a body httpx
# can't decompress, which we'd then return as garbage without Content-Encoding.
REQUEST_EXCLUDED_HEADERS = HOP_BY_HOP_HEADERS | {'accept-encoding'}


def resolve_endpoint(path, method):
    """
    Find the active endpoint registered for this path + method.
    Returns (endpoint, allowed_methods); endpoint is None when nothing matches.
    """
    candidates = Endpoint.objects.select_related('domain').filter(
        is_active=True, domain__is_active=True,
    )
    matching = [e for e in candidates if e.matches(path)]
    # Prefer exact (static) paths over placeholder paths like /users/{id}
    matching.sort(key=lambda e: e.is_dynamic)
    for endpoint in matching:
        if endpoint.method == method:
            return endpoint, []
    return None, sorted({e.method for e in matching})


@csrf_exempt
def proxy_view(request, subpath=''):
    """
    Path-based API proxy.
    /api/proxy/<path> is looked up against the registered endpoints; the request
    is forwarded to the endpoint's domain with the domain's credentials attached,
    and the upstream response is returned as-is.
    """
    path = normalize_path(subpath)
    method = request.method.upper()

    endpoint, allowed = resolve_endpoint(path, method)
    if endpoint is None:
        if allowed:
            response = JsonResponse(
                {'error': f'Method {method} is not allowed for {path}.', 'allowed_methods': allowed},
                status=405,
            )
            response['Allow'] = ', '.join(allowed)
            return response
        return JsonResponse({'error': f'No endpoint registered for {path}.'}, status=404)

    domain = endpoint.domain
    auth_headers = domain.auth_headers()
    overridden = {k.lower() for k in auth_headers}

    # Forward client headers, letting the domain's credentials/extra headers win
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in REQUEST_EXCLUDED_HEADERS and k.lower() not in overridden
    }
    headers.update(auth_headers)

    params = [(k, v) for k, values in request.GET.lists() for v in values]
    params.extend(domain.auth_params().items())

    try:
        with httpx.Client(timeout=domain.timeout, follow_redirects=True) as client:
            upstream_response = client.request(
                method=method,
                url=domain.build_url(path),
                params=params or None,
                headers=headers,
                content=request.body or None,
                auth=domain.basic_auth(),
            )

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
