from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
import httpx
import json

from .models import Domain, Endpoint


def make_response(status_code=200, payload=None):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = {'content-type': 'application/json'}
    mock_resp.content = json.dumps(payload if payload is not None else {}).encode('utf-8')
    return mock_resp


class ApiProxyTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.github = Domain.objects.create(name='github', base_url='https://api.github.com/')
        Endpoint.objects.create(domain=self.github, path='zen', method='GET')
        Endpoint.objects.create(domain=self.github, path='/users/{username}/repos', method='GET')

    def test_unknown_path_returns_404(self):
        response = self.client.get('/api/proxy/does-not-exist')
        self.assertEqual(response.status_code, 404)
        self.assertIn('No endpoint registered', response.json()['error'])

    def test_wrong_method_returns_405(self):
        response = self.client.post('/api/proxy/zen')
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response['Allow'], 'GET')

    def test_inactive_domain_returns_404(self):
        self.github.is_active = False
        self.github.save()
        response = self.client.get('/api/proxy/zen')
        self.assertEqual(response.status_code, 404)

    @patch('httpx.Client.request')
    def test_get_forwards_to_domain(self, mock_request):
        payload = {"random_field_123": "sample", "nested": {"dynamic_key": True}}
        mock_request.return_value = make_response(200, payload)

        response = self.client.get('/api/proxy/zen/?page=2')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['method'], 'GET')
        self.assertEqual(kwargs['url'], 'https://api.github.com/zen')
        self.assertEqual(kwargs['params'], [('page', '2')])
        self.assertIsNone(kwargs['auth'])

    @patch('httpx.Client.request')
    def test_client_accept_encoding_not_forwarded(self, mock_request):
        mock_request.return_value = make_response()

        self.client.get('/api/proxy/zen', HTTP_ACCEPT_ENCODING='gzip, deflate, br')

        _, kwargs = mock_request.call_args
        self.assertNotIn('accept-encoding', {k.lower() for k in kwargs['headers']})

    @patch('httpx.Client.request')
    def test_placeholder_path_matches(self, mock_request):
        mock_request.return_value = make_response(200, [{"id": 1}])

        response = self.client.get('/api/proxy/users/octocat/repos')

        self.assertEqual(response.status_code, 200)
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['url'], 'https://api.github.com/users/octocat/repos')

    @patch('httpx.Client.request')
    def test_post_forwards_raw_body(self, mock_request):
        Endpoint.objects.create(domain=self.github, path='/items', method='POST')
        mock_request.return_value = make_response(201, {"id": 7})

        body = json.dumps({"title": "New Item"})
        response = self.client.post('/api/proxy/items', data=body, content_type='application/json')

        self.assertEqual(response.status_code, 201)
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['method'], 'POST')
        self.assertEqual(kwargs['content'], body.encode('utf-8'))
        self.assertEqual(kwargs['headers']['Content-Type'], 'application/json')

    @patch('httpx.Client.request')
    def test_bearer_token_overrides_client_authorization(self, mock_request):
        self.github.auth_type = Domain.AUTH_BEARER
        self.github.token = 'secret-token'
        self.github.save()
        mock_request.return_value = make_response()

        self.client.get('/api/proxy/zen', HTTP_AUTHORIZATION='Bearer client-token')

        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer secret-token')
        self.assertEqual([k for k in kwargs['headers'] if k.lower() == 'authorization'], ['Authorization'])

    @patch('httpx.Client.request')
    def test_basic_auth(self, mock_request):
        self.github.auth_type = Domain.AUTH_BASIC
        self.github.username = 'user'
        self.github.password = 'pass'
        self.github.save()
        mock_request.return_value = make_response()

        self.client.get('/api/proxy/zen')

        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['auth'], ('user', 'pass'))

    @patch('httpx.Client.request')
    def test_api_key_header_and_query(self, mock_request):
        mock_request.return_value = make_response()

        self.github.auth_type = Domain.AUTH_API_KEY_HEADER
        self.github.api_key_name = 'X-API-Key'
        self.github.api_key_value = 'k1'
        self.github.save()
        self.client.get('/api/proxy/zen')
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['headers']['X-API-Key'], 'k1')

        self.github.auth_type = Domain.AUTH_API_KEY_QUERY
        self.github.api_key_name = 'api_key'
        self.github.save()
        self.client.get('/api/proxy/zen')
        _, kwargs = mock_request.call_args
        self.assertIn(('api_key', 'k1'), kwargs['params'])

    @patch('httpx.Client.request')
    def test_upstream_error_status_relayed(self, mock_request):
        mock_request.return_value = make_response(404, {"detail": "Not found"})

        response = self.client.get('/api/proxy/zen')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Not found"})

    @patch('httpx.Client.request')
    def test_upstream_timeout_returns_504(self, mock_request):
        mock_request.side_effect = httpx.TimeoutException("Connection timed out")

        response = self.client.get('/api/proxy/zen')
        self.assertEqual(response.status_code, 504)
        self.assertIn("Upstream request timed out.", response.json()['error'])

    @patch('httpx.Client.request')
    def test_upstream_connection_failure_returns_502(self, mock_request):
        mock_request.side_effect = httpx.RequestError("DNS lookup failed")

        response = self.client.get('/api/proxy/zen')
        self.assertEqual(response.status_code, 502)
        self.assertIn("Failed to reach upstream server.", response.json()['error'])
