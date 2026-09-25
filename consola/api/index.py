"""Vercel Python Function: secrets and PostgreSQL initialized only on API use."""
import json
import hmac
import os
import sys
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import handler_for, validate_config

_delegate = None
_delegate_lock = threading.Lock()


def _log_storage_failure(exc):
    # Log only safe diagnostics; never include DSNs, request bodies, or credentials.
    print(json.dumps({'event': 'telemetry_storage_failure', 'type': type(exc).__name__,
                      'sqlstate': getattr(exc, 'sqlstate', None)}), file=sys.stderr, flush=True)

def configured_handler():
    global _delegate
    if _delegate is None:
        with _delegate_lock:
            if _delegate is None:
                config = validate_config(json.loads(os.environ['CONSOLE_CONFIG_JSON']))
                from postgres_store import PostgresStore
                store = PostgresStore(os.environ['DATABASE_URL'])
                base = handler_for(config, store)

                def do_get(self):
                    try:
                        base.do_GET(self)
                    except Exception as exc:
                        _log_storage_failure(exc)
                        self.reply(503, {'error': 'Almacenamiento no disponible; reintentar'})

                def do_post(self):
                    try:
                        base.do_POST(self)
                    except Exception as exc:
                        _log_storage_failure(exc)
                        self.reply(503, {'error': 'Almacenamiento no disponible; reintentar el mismo mensaje'})

                _delegate = type('ConfiguredHandler', (base,), {'do_GET': do_get, 'do_POST': do_post})
    return _delegate


class handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass  # Avoid writing sensor credentials, bodies, or request paths to logs.

    def reply(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        origin = self.headers.get('Origin')
        try:
            allowed_origins = json.loads(os.environ.get('CONSOLE_CONFIG_JSON', '{}')).get('allowed_origins', [])
        except (TypeError, ValueError):
            allowed_origins = []
        if origin in allowed_origins:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(data)

    def auth(self, key):
        return hmac.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer ' + key).encode())

    def _dispatch(self, method):
        original_path = self.path
        params = parse_qs(urlsplit(original_path).query)
        self.path = params.get('path', [urlsplit(original_path).path])[0]
        try:
            getattr(configured_handler(), method)(self)
        except Exception:
            self.reply(503, {'error': 'API no configurada; definir CONSOLE_CONFIG_JSON y DATABASE_URL'})
        finally:
            self.path = original_path

    def do_GET(self):
        original_path = self.path
        params = parse_qs(urlsplit(original_path).query)
        endpoint = params.get('path', [urlsplit(original_path).path])[0]
        if endpoint.rstrip('/') == '/health':
            return self.reply(200, {'status': 'ok', 'configured': bool(os.environ.get('CONSOLE_CONFIG_JSON') and os.environ.get('DATABASE_URL'))})
        self._dispatch('do_GET')

    def do_POST(self):
        self._dispatch('do_POST')

    def do_OPTIONS(self):
        self._dispatch('do_OPTIONS')
