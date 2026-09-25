import json
import io
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from server import Store, handler_for
from api.index import handler as vercel_handler


class ReceiverTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'test.db')
        self.config = {'read_key': 'r'*40, 'allowed_origins': ['https://luiscontreras73.github.io'],
                       'devices': {'nivel_01': {'key': 'n'*40, 'station': 'test', 'fields': ['nivel_cm', 'temp_c']},
                                   'suelo_01': {'key': 's'*40, 'station': 'test', 'fields': ['suelo']}}}
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.config, self.store))
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        self.url = f'http://127.0.0.1:{self.http.server_port}'
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.worker.join()
        self.temp.cleanup()

    def request(self, method, path, key='', body=None, origin=None):
        headers = {'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        req = Request(self.url+path, method=method, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            data = response.read()
            return response.status, json.loads(data) if data else {}, response.headers

    def send(self, device='nivel_01', delta=0, **values):
        return self.request('POST', '/v1/telemetry', self.config['devices'][device]['key'],
                            {'device': device, 'ts': (self.now+timedelta(seconds=delta)).isoformat(), **values})

    def test_sensor_merge_zero_and_persistence(self):
        self.assertEqual(self.send(nivel_cm=123.4)[0], 201)
        self.assertEqual(self.send(device='suelo_01', suelo=0)[0], 201)
        latest = self.request('GET', '/v1/stations/test/latest', 'r'*40)[1]
        self.assertEqual(latest['latest']['nivel_cm']['value'], 123.4)
        self.assertEqual(latest['latest']['suelo']['value'], 0)
        persisted = Store(self.store.path).snapshot('test')
        self.assertEqual(persisted['latest'], latest['latest'])
        self.assertEqual(len(persisted['history']), 2)

    def test_out_of_order_and_duplicate(self):
        self.send(nivel_cm=125)
        self.send(delta=-30, nivel_cm=100)
        self.assertEqual(self.send(nivel_cm=125)[1]['duplicate'], True)
        latest = self.store.snapshot('test')
        self.assertEqual(latest['latest']['nivel_cm']['value'], 125)
        self.assertEqual(len(latest['history']), 2)

    def test_scoped_authentication(self):
        self.assertEqual(self.request('GET', '/v1/stations/test/latest', 'n'*40)[0], 401)
        self.assertEqual(self.request('POST', '/v1/telemetry', 'r'*40, {})[0], 401)
        self.assertEqual(self.send(suelo=50)[0], 400)
        self.assertEqual(self.request('POST', '/v1/telemetry', 'n'*40, {'device': 'suelo_01', 'ts': self.now.isoformat(), 'nivel_cm': 1})[0], 400)

    def test_invalid_measurements(self):
        for value in [None, True, '15', -1, float('nan'), float('inf')]:
            with self.subTest(value=value):
                self.assertEqual(self.send(nivel_cm=value)[0], 400)
        self.assertEqual(self.send(device='suelo_01', suelo=101)[0], 400)
        self.assertEqual(self.send(delta=300, nivel_cm=100)[0], 400)
        self.assertEqual(self.send()[0], 400)
        self.assertEqual(self.request('POST', '/v1/telemetry', 'n'*40, {'device': 'nivel_01', 'ts': '2026-09-25T12:00:00', 'nivel_cm': 1})[0], 400)

    def test_empty_station_and_cors(self):
        status, data, headers = self.request('GET', '/v1/stations/test/latest', 'r'*40, origin='https://luiscontreras73.github.io')
        self.assertEqual(status, 200)
        self.assertEqual(data['latest'], {})
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'https://luiscontreras73.github.io')
        self.assertEqual(self.request('OPTIONS', '/v1/telemetry', origin='https://evil.example')[0], 403)
        self.assertEqual(self.request('OPTIONS', '/v1/telemetry', origin='https://luiscontreras73.github.io')[0], 204)
        self.assertEqual(self.request('GET', '/v1/stations/unknown/latest', 'r'*40)[0], 404)


class VercelCorsTest(unittest.TestCase):
    def test_reply_includes_cors_only_for_configured_origin(self):
        class ResponseProbe:
            def __init__(self, origin):
                self.headers = {'Origin': origin}
                self.sent_headers = {}
                self.wfile = io.BytesIO()

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.sent_headers[name] = value

            def end_headers(self):
                pass

        configured = {'allowed_origins': ['https://luiscontreras73.github.io']}
        with patch.dict(os.environ, {'CONSOLE_CONFIG_JSON': json.dumps(configured)}):
            allowed = ResponseProbe('https://luiscontreras73.github.io')
            vercel_handler.reply(allowed, 401, {'error': 'Clave inválida'})
            denied = ResponseProbe('https://example.invalid')
            vercel_handler.reply(denied, 401, {'error': 'Clave inválida'})

        self.assertEqual(allowed.sent_headers['Access-Control-Allow-Origin'], configured['allowed_origins'][0])
        self.assertEqual(allowed.sent_headers['Vary'], 'Origin')
        self.assertNotIn('Access-Control-Allow-Origin', denied.sent_headers)


if __name__ == '__main__':
    unittest.main(verbosity=2)
