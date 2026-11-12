"""Настройки из окружения/.env. Секреты не записываются в исходный код."""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)


def local_secret(filename, environment_name, legacy_name=None):
    value = os.getenv(environment_name) or (
        os.getenv(legacy_name) if legacy_name else None
    )
    if value:
        if len(value) < 32:
            raise ValueError(f"{environment_name} должен содержать минимум 32 символа")
        return value
    path = ROOT / filename
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 32:
        raise ValueError(f"Файл {filename} содержит слишком короткий секрет")
    return value


def session_secret():
    # Прежний ключ можно сохранить; формат cookie всё равно требует нового входа.
    return local_secret(".session_secret", "SESSION_SECRET_KEY", "FLASK_SECRET_KEY")


def gps_token():
    return local_secret(".gps_token", "GPS_INGEST_TOKEN")


def https_enabled():
    return os.getenv("SESSION_HTTPS", os.getenv("FLASK_HTTPS", "0")) == "1"


def database_options():
    """Одинаковые настройки для сервера и локальных команд."""
    return {
        "host": os.getenv("TRUCKS_DB_HOST", "localhost"),
        "port": int(os.getenv("TRUCKS_DB_PORT", "5432")),
        "dbname": os.getenv("TRUCKS_DB_NAME", "trucks_mko"),
        "user": os.getenv("TRUCKS_DB_USER", "postgres"),
    }
