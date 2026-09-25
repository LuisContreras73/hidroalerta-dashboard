"""Genera credenciales independientes. No imprime secretos ni sobrescribe archivos."""
import json
import secrets
from pathlib import Path

path = Path(__file__).with_name("credentials.local.json")
config = {"read_key": secrets.token_urlsafe(32),
          "allowed_origins": ["https://luiscontreras73.github.io", "http://127.0.0.1:8765", "http://localhost:8765"],
          "devices": {
              "nivel_01": {"key": secrets.token_urlsafe(32), "station": "est_santo_domingo_01", "fields": ["nivel_cm", "temp_c", "bateria_v", "rssi"]},
              "suelo_01": {"key": secrets.token_urlsafe(32), "station": "est_santo_domingo_01", "fields": ["suelo", "temp_c", "bateria_v", "rssi"]}}}
with path.open("x", encoding="utf-8") as handle:
    json.dump(config, handle, indent=2)
print("Credenciales creadas en consola/credentials.local.json (excluido de Git).")
