-- ECHO-UNIT: установка ТОЛЬКО в новую пустую базу.
-- Не запускайте этот файл в существующей базе. Он не является миграцией.
BEGIN;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name IN
            ('trucks', 'fleet_trips', 'fleet_positions', 'fleet_position_history', 'fleet_events', 'fleet_users')
    ) THEN
        RAISE EXCEPTION 'Fleet tables already exist; this script is only for an empty database';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS trucks (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'На месте'
        CHECK (status IN ('В пути', 'На месте', 'На ремонте')),
    driver VARCHAR(100) NOT NULL DEFAULT 'Не назначен'
);

CREATE TABLE IF NOT EXISTS fleet_trips (
    id BIGSERIAL PRIMARY KEY,
    truck_id INTEGER NOT NULL REFERENCES trucks(id),
    origin VARCHAR(100) NOT NULL,
    destination VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Запланирован'
        CHECK (status IN ('Запланирован', 'В пути', 'Завершён')),
    departure_at TIMESTAMPTZ DEFAULT NOW(),
    eta_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS fleet_one_trip_in_transit_МКО
    ON fleet_trips (truck_id) WHERE status = 'В пути';

CREATE TABLE IF NOT EXISTS fleet_positions (
    truck_id INTEGER PRIMARY KEY REFERENCES trucks(id),
    latitude NUMERIC(10, 6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude NUMERIC(10, 6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE fleet_positions
    ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'unknown';
ALTER TABLE fleet_positions
    ADD COLUMN IF NOT EXISTS speed_kmh NUMERIC(6, 1);

CREATE TABLE IF NOT EXISTS fleet_position_history (
    id BIGSERIAL PRIMARY KEY,
    truck_id INTEGER NOT NULL REFERENCES trucks(id),
    latitude NUMERIC(10, 6) NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude NUMERIC(10, 6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    speed_kmh NUMERIC(6, 1) CHECK (speed_kmh BETWEEN 0 AND 250),
    source VARCHAR(16) NOT NULL CHECK (source IN ('simulated', 'manual')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS fleet_history_truck_time_idx
    ON fleet_position_history (truck_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS fleet_events (
    id BIGSERIAL PRIMARY KEY,
    truck_id INTEGER REFERENCES trucks(id),
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fleet_users (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE fleet_users
    ADD COLUMN IF NOT EXISTS role VARCHAR(16) NOT NULL DEFAULT 'dispatcher'
        CHECK (role IN ('admin', 'dispatcher'));
ALTER TABLE fleet_users
    ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;

-- Скрипт рассчитан на новую базу; существующих пользователей здесь нет.
-- Первого администратора на новой базе назначаем командой create_admin.py.
COMMIT;
