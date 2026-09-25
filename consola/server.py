"""Receptor HTTP de la consola. Sin dependencias; desplegar detrás de HTTPS."""
import hashlib
import hmac
import json
import math
import os
import re
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

LIMITS = {"nivel_cm": (0, 100000), "suelo": (0, 100), "temp_c": (-80, 100),
          "bateria_v": (0, 60), "rssi": (-200, 0), "caudal_m3s": (0, 100000)}
ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("ts debe ser ISO 8601 con zona horaria")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("ts necesita zona horaria, por ejemplo Z")
    return dt.astimezone(timezone.utc)


def validate(body, device, now):
    if not isinstance(body, dict) or set(body) - {"device", "ts", *LIMITS}:
        raise ValueError("Campos desconocidos; consultar el contrato de telemetría")
    if body.get("device") != device:
        raise ValueError("device no coincide con la clave del sensor")
    dt = timestamp(body.get("ts"))
    if dt.timestamp() > now.timestamp() + 120:
        raise ValueError("ts está más de 120 segundos en el futuro")
    metrics = {k: v for k, v in body.items() if k in LIMITS}
    if not metrics:
        raise ValueError("Se necesita al menos una medición")
    for k, v in metrics.items():
        low, high = LIMITS[k]
        if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"{k} debe ser un número entre {low} y {high}")
    return {"device": device, "ts": dt.isoformat().replace("+00:00", "Z"), **metrics}


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS readings (id TEXT PRIMARY KEY, station TEXT, device TEXT, ts TEXT, received_at TEXT, body TEXT)")
            db.execute("CREATE INDEX IF NOT EXISTS readings_station ON readings(station, ts DESC)")
            db.execute("CREATE TABLE IF NOT EXISTS latest (station TEXT, metric TEXT, ts TEXT, device TEXT, value REAL, received_at TEXT, PRIMARY KEY(station, metric))")

    def connect(self):
        return sqlite3.connect(self.path, timeout=15)

    def insert(self, station, reading, received):
        body = json.dumps(reading, sort_keys=True, separators=(",", ":"))
        identity = hashlib.sha256((station + body).encode()).hexdigest()
        with self.connect() as db:
            inserted = db.execute("INSERT OR IGNORE INTO readings VALUES (?,?,?,?,?,?)",
                                  (identity, station, reading["device"], reading["ts"], received, body)).rowcount
            if inserted:
                for key, value in reading.items():
                    if key in LIMITS:
                        db.execute("""INSERT INTO latest VALUES (?,?,?,?,?,?)
                            ON CONFLICT(station, metric) DO UPDATE SET ts=excluded.ts, device=excluded.device,
                            value=excluded.value, received_at=excluded.received_at
                            WHERE julianday(excluded.ts)>julianday(latest.ts)""",
                                   (station, key, reading["ts"], reading["device"], value, received))
                # Historial acotado por estación; latest conserva la última lectura por campo.
                db.execute("DELETE FROM readings WHERE station=? AND id NOT IN (SELECT id FROM readings WHERE station=? ORDER BY julianday(ts) DESC LIMIT 10000)", (station, station))
        return identity, bool(inserted)

    def snapshot(self, station):
        with self.connect() as db:
            rows = db.execute("SELECT metric, value, ts, device, received_at FROM latest WHERE station=?", (station,)).fetchall()
            history = db.execute("SELECT body FROM readings WHERE station=? ORDER BY julianday(ts) DESC LIMIT 120", (station,)).fetchall()
        return {"station": station, "server_time": datetime.now(timezone.utc).isoformat(),
                "latest": {k: {"value": v, "ts": ts, "device": device, "received_at": received} for k, v, ts, device, received in rows},
                "history": [json.loads(row[0]) for row in reversed(history)]}


def handler_for(config, store):
    devices = config["devices"]
    origins = set(config["allowed_origins"])

    class Handler(BaseHTTPRequestHandler):
        server_version = "HidroAlertaConsola/1"

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass  # No registrar cabeceras, claves ni URL arbitrarias.

        def reply(self, status, payload):
            data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = self.headers.get("Origin")
            if origin in origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(data)

        def auth(self, key):
            return hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + key).encode())

        def do_OPTIONS(self):
            if self.headers.get("Origin") not in origins:
                return self.reply(403, {"error": "Origen no autorizado"})
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/health":
                return self.reply(200, {"status": "ok"})
            match = re.fullmatch(r"/v1/stations/([a-zA-Z0-9_-]{1,64})/latest", path)
            if not match:
                return self.reply(404, {"error": "Ruta inexistente"})
            if not self.auth(config["read_key"]):
                return self.reply(401, {"error": "Clave de lectura inválida"})
            station = match[1]
            if station not in {d["station"] for d in devices.values()}:
                return self.reply(404, {"error": "Estación desconocida"})
            self.reply(200, store.snapshot(station))

        def do_POST(self):
            if urlsplit(self.path).path != "/v1/telemetry":
                return self.reply(404, {"error": "Ruta inexistente"})
            match = next(((name, d) for name, d in devices.items() if self.auth(d["key"])), None)
            if not match:
                return self.reply(401, {"error": "Clave del sensor inválida"})
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return self.reply(415, {"error": "Usar application/json"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.reply(400, {"error": "Content-Length inválido"})
            if not 0 < size <= 8192:
                return self.reply(413, {"error": "Cuerpo vacío o mayor a 8192 bytes"})
            try:
                now = datetime.now(timezone.utc)
                reading = validate(json.loads(self.rfile.read(size)), match[0], now)
                if (set(reading) & set(LIMITS)) - set(match[1]["fields"]):
                    raise ValueError("Este sensor no tiene permiso para esos campos")
            except (ValueError, UnicodeDecodeError, OverflowError) as exc:
                return self.reply(400, {"error": str(exc)})
            identity, inserted = store.insert(match[1]["station"], reading, now.isoformat())
            self.reply(201 if inserted else 200, {"ok": True, "id": identity, "duplicate": not inserted})

    return Handler


def load_config(path):
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8")))


def validate_config(config):
    keys = [config["read_key"], *(v["key"] for v in config["devices"].values())]
    if not config["devices"] or any(not isinstance(k, str) or len(k) < 32 or k.startswith("ghp_") for k in keys) or len(keys) != len(set(keys)):
        raise ValueError("Usar claves únicas de al menos 32 caracteres; nunca tokens de GitHub")
    for device, values in config["devices"].items():
        if not ID.fullmatch(device) or not ID.fullmatch(values["station"]):
            raise ValueError("Identificador inválido")
        if not values["fields"] or set(values["fields"]) - set(LIMITS):
            raise ValueError("Campos del sensor inválidos")
    if not config["allowed_origins"] or any(not isinstance(origin, str) or not origin.startswith(("http://", "https://")) or urlsplit(origin).path for origin in config["allowed_origins"]):
        raise ValueError("Definir orígenes CORS completos, sin rutas ni comodines")
    return config


if __name__ == "__main__":
    config = load_config(os.environ.get("CONSOLE_CONFIG", str(Path(__file__).with_name("credentials.local.json"))))
    database = os.environ.get("CONSOLE_DB", str(Path(__file__).with_name("telemetry.db")))
    host, port = os.environ.get("CONSOLE_HOST", "127.0.0.1"), int(os.environ.get("PORT", "8787"))
    server = ThreadingHTTPServer((host, port), handler_for(config, Store(database)))
    print(f"Receptor consola escuchando en http://{host}:{port}; claves fuera de los registros", flush=True)
    server.serve_forever()
