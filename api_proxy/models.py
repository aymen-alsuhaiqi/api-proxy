import re

from django.db import models


def normalize_path(path):
    """Ensure a leading slash and drop any trailing slash (except for root)."""
    path = '/' + (path or '').strip().strip('/')
    return path


class Domain(models.Model):
    """An upstream service the proxy can forward requests to."""

    AUTH_NONE = 'none'
    AUTH_BEARER = 'bearer'
    AUTH_BASIC = 'basic'
    AUTH_API_KEY_HEADER = 'api_key_header'
    AUTH_API_KEY_QUERY = 'api_key_query'
    AUTH_CHOICES = [
        (AUTH_NONE, 'No authentication'),
        (AUTH_BEARER, 'Bearer token'),
        (AUTH_BASIC, 'Basic auth (username / password)'),
        (AUTH_API_KEY_HEADER, 'API key in header'),
        (AUTH_API_KEY_QUERY, 'API key in query string'),
    ]

    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(help_text='e.g. https://api.github.com')
    is_active = models.BooleanField(default=True)
    timeout = models.FloatField(default=30.0, help_text='Upstream timeout in seconds')

    auth_type = models.CharField(max_length=20, choices=AUTH_CHOICES, default=AUTH_NONE)
    token = models.CharField(max_length=1024, blank=True, help_text='Bearer token')
    username = models.CharField(max_length=255, blank=True, help_text='Basic auth username')
    password = models.CharField(max_length=255, blank=True, help_text='Basic auth password')
    api_key_name = models.CharField(
        max_length=255, blank=True,
        help_text='Header or query param name, e.g. X-API-Key or api_key',
    )
    api_key_value = models.CharField(max_length=1024, blank=True)
    extra_headers = models.JSONField(
        default=dict, blank=True,
        help_text='Extra headers sent with every request, e.g. {"Accept": "application/json"}',
    )

    def __str__(self):
        return f'{self.name} ({self.base_url})'

    def build_url(self, path):
        return self.base_url.rstrip('/') + normalize_path(path)

    def auth_headers(self):
        headers = dict(self.extra_headers or {})
        if self.auth_type == self.AUTH_BEARER and self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        elif self.auth_type == self.AUTH_API_KEY_HEADER and self.api_key_name:
            headers[self.api_key_name] = self.api_key_value
        return headers

    def auth_params(self):
        if self.auth_type == self.AUTH_API_KEY_QUERY and self.api_key_name:
            return {self.api_key_name: self.api_key_value}
        return {}

    def basic_auth(self):
        if self.auth_type == self.AUTH_BASIC and self.username:
            return (self.username, self.password)
        return None


class Endpoint(models.Model):
    """A path + HTTP method exposed through the proxy for a given domain.

    Paths may contain placeholders such as /users/{id}/repos, which match any
    single path segment.
    """

    METHOD_CHOICES = [(m, m) for m in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS')]

    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name='endpoints')
    path = models.CharField(max_length=500, help_text='e.g. /zen or /users/{username}')
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default='GET')
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['path', 'method'], name='unique_endpoint_path_method'),
        ]
        ordering = ['path', 'method']

    def __str__(self):
        return f'{self.method} {self.path} -> {self.domain.name}'

    def save(self, *args, **kwargs):
        self.path = normalize_path(self.path)
        self.method = self.method.upper()
        super().save(*args, **kwargs)

    @property
    def is_dynamic(self):
        return '{' in self.path

    def matches(self, path):
        """Return True if the incoming (normalized) path matches this endpoint."""
        if not self.is_dynamic:
            return self.path == path
        pattern = re.sub(r'\\\{[^/]+?\\\}', '[^/]+', re.escape(self.path))
        return re.fullmatch(pattern, path) is not None
