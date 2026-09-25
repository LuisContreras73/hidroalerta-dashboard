"""Prueba visual aislada: sólo localhost, estación test, datos sintéticos explícitos."""
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from http.server import ThreadingHTTPServer
from server import Store, handler_for

with tempfile.TemporaryDirectory() as folder:
    store = Store(Path(folder) / 'fixture.db')
    config = {'read_key': 'test-read-key-not-for-production-123456',
              'allowed_origins': ['http://127.0.0.1:8765'],
              'devices': {'test_nivel': {'key': 'test-level-key-not-for-production-123', 'station': 'test', 'fields': ['nivel_cm']},
                          'test_suelo': {'key': 'test-soil-key-not-for-production-1234', 'station': 'test', 'fields': ['suelo']}}}
    now = datetime.now(timezone.utc).isoformat()
    store.insert('test', {'device': 'test_nivel', 'ts': now, 'nivel_cm': 123}, now)
    store.insert('test', {'device': 'test_suelo', 'ts': now, 'suelo': 42}, now)
    print('Fixture sintético: http://127.0.0.1:8788; estación test', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8788), handler_for(config, store)).serve_forever()
