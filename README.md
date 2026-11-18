# API Proxy Service

A dynamic HTTP API Proxy endpoint built with Django that relays requests to arbitrary upstream URLs and returns their response directly, supporting dynamic, unstructured, and random schemas without requiring predefined models or serialization constraints.

## Endpoint

- **Primary URL**: `/api/proxy/`
- **Alias URL**: `/api/gateway/`
- **Supported Methods**: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, etc.

---

## Usage Examples

### 1. Simple GET Request via Query Parameter
Call any target URL via the `?url=` parameter:

```bash
curl -X GET "http://127.0.0.1:8000/api/proxy/?url=https://api.github.com/zen"
```

### 2. POST / Custom Request with Payload via JSON Body
Send a JSON payload specifying the target URL, method, headers, and body data:

```bash
curl -X POST "http://127.0.0.1:8000/api/proxy/" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://httpbin.org/post",
    "method": "POST",
    "headers": {
      "Authorization": "Bearer sample_token"
    },
    "data": {
      "any_random_key": "any_value",
      "nested_list": [1, 2, 3]
    }
  }'
```

### 3. Dynamic Response Schema
Whatever the upstream server returns (arbitrary JSON schema, array of objects, XML, plain text, HTML, binary stream), the proxy returns it directly with:
- The exact **HTTP status code** from the upstream server (e.g. `200`, `201`, `400`, `404`, etc.)
- The original **Content-Type** header
- Raw payload without enforcing static schemas

### 4. Error Handling
- **400 Bad Request**: If `url` is missing or has an invalid scheme (only HTTP/HTTPS allowed).
- **502 Bad Gateway**: If the upstream host is unreachable or DNS lookup fails.
- **504 Gateway Timeout**: If the upstream request times out.
