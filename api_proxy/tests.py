from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
import httpx
import json

class ApiProxyTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('proxy')

    def test_missing_url_returns_400(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'Target URL is required.')

    def test_invalid_scheme_returns_400(self):
        response = self.client.get(f"{self.url}?url=ftp://example.com/file")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('Invalid URL scheme', data['error'])

    @patch('httpx.Client.request')
    def test_get_proxy_returns_random_json_schema(self, mock_request):
        # Arbitrary / random response structure (nested dict with list, integers, strings)
        random_response_payload = {
            "random_field_123": "sample",
            "numbers": [1, 2, 3],
            "nested": {
                "dynamic_key": True,
                "metadata": None
            }
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'content-type': 'application/json'}
        mock_resp.content = json.dumps(random_response_payload).encode('utf-8')
        mock_request.return_value = mock_resp

        response = self.client.get(f"{self.url}?url=https://api.randomsite.com/dynamic-data")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), random_response_payload)
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs['method'], 'GET')
        self.assertEqual(kwargs['url'], 'https://api.randomsite.com/dynamic-data')

    @patch('httpx.Client.request')
    def test_post_proxy_with_body_returns_unstructured_array(self, mock_request):
        # Target server returns an unstructured list/array response
        array_response_payload = [{"id": 1}, {"foo": "bar", "unknown": [99, 100]}]
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.headers = {'content-type': 'application/json'}
        mock_resp.content = json.dumps(array_response_payload).encode('utf-8')
        mock_request.return_value = mock_resp

        post_body = {
            "url": "https://service.domain.org/items",
            "method": "POST",
            "data": {"title": "New Item"}
        }

        response = self.client.post(
            self.url,
            data=json.dumps(post_body),
            content_type="application/json"
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), array_response_payload)
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['method'], 'POST')
        self.assertEqual(kwargs['url'], 'https://service.domain.org/items')
        self.assertEqual(kwargs['json'], {"title": "New Item"})

    @patch('httpx.Client.request')
    def test_upstream_error_status_relayed(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.headers = {'content-type': 'application/json'}
        mock_resp.content = json.dumps({"detail": "Not found"}).encode('utf-8')
        mock_request.return_value = mock_resp

        response = self.client.get(f"{self.url}?url=https://example.com/notfound")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Not found"})

    @patch('httpx.Client.request')
    def test_upstream_timeout_returns_504(self, mock_request):
        mock_request.side_effect = httpx.TimeoutException("Connection timed out")

        response = self.client.get(f"{self.url}?url=https://slow-api.com/delay")
        self.assertEqual(response.status_code, 504)
        self.assertIn("Upstream request timed out.", response.json()['error'])

    @patch('httpx.Client.request')
    def test_upstream_connection_failure_returns_502(self, mock_request):
        mock_request.side_effect = httpx.RequestError("DNS lookup failed")

        response = self.client.get(f"{self.url}?url=https://invalid-host.unknown/data")
        self.assertEqual(response.status_code, 502)
        self.assertIn("Failed to reach upstream server.", response.json()['error'])

    def test_gateway_alias_works(self):
        alias_url = reverse('gateway_alias')
        response = self.client.get(alias_url)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Target URL is required.')
