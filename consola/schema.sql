CREATE TABLE IF NOT EXISTS console_readings (
 id TEXT PRIMARY KEY, station TEXT NOT NULL, device TEXT NOT NULL,
 ts TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL, body TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS console_readings_station ON console_readings(station, ts DESC);
CREATE TABLE IF NOT EXISTS console_latest (
 station TEXT NOT NULL, metric TEXT NOT NULL, ts TIMESTAMPTZ NOT NULL,
 device TEXT NOT NULL, value DOUBLE PRECISION NOT NULL, received_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(station, metric)
);
