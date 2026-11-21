# API Proxy Service

A Django API gateway that forwards requests to registered upstream domains. You register **domains** (base URL + credentials) and their **endpoints** (path + HTTP method). A request to `/api/proxy/<path>` is matched against the registered endpoints, sent to the matching domain with its credentials attached, and the upstream response is returned as-is.

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Then open `http://127.0.0.1:8000/admin/` to add domains and endpoints.

## Configuration

### Domain
| Field | Description |
|---|---|
| `name` | Unique label, e.g. `github` |
| `base_url` | Upstream base URL, e.g. `https://api.github.com` |
| `is_active` | Disable to stop proxying all of the domain's endpoints |
| `timeout` | Upstream timeout in seconds (default 30) |
| `auth_type` | `none`, `bearer`, `basic`, `api_key_header`, `api_key_query` |
| `token` | Used by `bearer` → `Authorization: Bearer <token>` |
| `username` / `password` | Used by `basic` |
| `api_key_name` / `api_key_value` | Used by `api_key_header` (header name) and `api_key_query` (query param name) |
| `extra_headers` | JSON object of headers sent with every request |

### Endpoint
| Field | Description |
|---|---|
| `domain` | The domain this endpoint belongs to |
| `path` | Path after `/api/proxy/`, e.g. `/zen`. Placeholders match one path segment: `/users/{username}/repos` |
| `method` | `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` |
| `is_active` | Disable to stop proxying this endpoint |

A `path` + `method` pair is unique across all domains. Exact paths take priority over placeholder paths.

## Usage

With a domain `https://api.github.com` and an endpoint `GET /zen`:

```bash
curl "http://127.0.0.1:8000/api/proxy/zen"
# -> GET https://api.github.com/zen (with the domain's credentials)
```

- Query strings are forwarded: `/api/proxy/search?q=x` → `<base_url>/search?q=x`
- The request body and `Content-Type` are forwarded unchanged.
- Client headers are forwarded, but the domain's credentials and `extra_headers` override them.
- The upstream status code, `Content-Type`, headers and body are returned unchanged.

## Error responses
| Status | When |
|---|---|
| `404` | No active endpoint is registered for the path |
| `405` | The path exists but not for this method (`Allow` header lists valid methods) |
| `502` | Upstream unreachable / DNS failure |
| `504` | Upstream timed out |

## Tests

```bash
python manage.py test api_proxy
```
