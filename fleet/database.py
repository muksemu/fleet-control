"""Синхронный psycopg: соединение и события в транзакции вызывающего кода."""

import os
import sys
from functools import lru_cache
from getpass import getpass

import psycopg
from psycopg.rows import dict_row

import config


@lru_cache(maxsize=1)
def get_db_password():
    password = os.getenv("TRUCKS_DB_PASSWORD")
    if password is not None:
        return password
    if sys.stdin.isatty():
        return getpass("Пароль PostgreSQL: ")
    raise psycopg.OperationalError("Укажите TRUCKS_DB_PASSWORD в окружении или .env")


def connect():
    return psycopg.connect(
        **config.database_options(),
        password=get_db_password(),
        row_factory=dict_row,
        connect_timeout=5,
    )


def add_event(conn, truck_id, description):
    conn.execute(
        "INSERT INTO fleet_events (truck_id, description) VALUES (%s, %s)",
        (truck_id, description),
    )
