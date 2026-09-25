"""Almacenamiento persistente para Vercel + PostgreSQL (por ejemplo Neon)."""
import hashlib
import json
from datetime import datetime, timezone
import psycopg
from server import LIMITS


class PostgresStore:
    def __init__(self, dsn):
        self.dsn = dsn

    def connect(self):
        return psycopg.connect(self.dsn, connect_timeout=5, options='-c statement_timeout=8000')

    def insert(self, station, reading, received):
        body = json.dumps(reading, sort_keys=True, separators=(',', ':'))
        identity = hashlib.sha256((station + body).encode()).hexdigest()
        with self.connect() as db:
            # Serializar sólo escrituras de una misma estación, incluida la retención.
            db.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (station,))
            inserted = db.execute('''INSERT INTO console_readings(id,station,device,ts,received_at,body)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING''',
                                  (identity, station, reading['device'], reading['ts'], received, body)).rowcount
            if inserted:
                for key, value in reading.items():
                    if key in LIMITS:
                        db.execute('''INSERT INTO console_latest(station,metric,ts,device,value,received_at)
                            VALUES (%s,%s,%s,%s,%s,%s)
                            ON CONFLICT(station,metric) DO UPDATE SET ts=excluded.ts,device=excluded.device,
                            value=excluded.value,received_at=excluded.received_at
                            WHERE excluded.ts > console_latest.ts''',
                                   (station, key, reading['ts'], reading['device'], value, received))
                db.execute('''DELETE FROM console_readings WHERE station=%s AND id NOT IN
                    (SELECT id FROM console_readings WHERE station=%s ORDER BY ts DESC LIMIT 10000)''', (station, station))
        return identity, bool(inserted)

    def snapshot(self, station):
        with self.connect() as db:
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            rows = db.execute('SELECT metric,value,ts,device,received_at FROM console_latest WHERE station=%s', (station,)).fetchall()
            history = db.execute('SELECT body FROM console_readings WHERE station=%s ORDER BY ts DESC LIMIT 120', (station,)).fetchall()
        return {'station': station, 'server_time': datetime.now(timezone.utc).isoformat(),
                'latest': {k: {'value': v, 'ts': ts.isoformat(), 'device': device, 'received_at': received.isoformat()} for k, v, ts, device, received in rows},
                'history': [json.loads(row[0]) for row in reversed(history)]}
