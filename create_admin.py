"""Только локальная первоначальная настройка: создать первого администратора.

Запуск в терминале владельца: python create_admin.py
Не является HTTP-адресом и не вызывается из браузера.
"""

import re
from getpass import getpass

from fleet.user_roles import ADMIN_LOCK_KEY


class AlreadyConfiguredError(Exception):
    """Администратор уже существует (второго через эту команду не создаём)."""


def create_first_admin(conn, name, email, password_hash):
    """Создать первого администратора атомарно. Возвращает его ID.

    Пароль сюда передаётся уже в виде хеша. Никаких автоматических повышений
    ранее зарегистрированных пользователей здесь нет.
    """
    # Один и тот же lock, который применяется в API для изменения ролей.
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (ADMIN_LOCK_KEY,))
    existing = conn.execute(
        "SELECT id FROM fleet_users WHERE role = 'admin' LIMIT 1"
    ).fetchone()
    if existing:
        raise AlreadyConfiguredError(
            "Администратор уже назначен. Ничего менять не нужно."
        )
    new_user = conn.execute(
        """
        INSERT INTO fleet_users (name, email, password_hash, role, active)
        VALUES (%s, %s, %s, 'admin', TRUE)
        RETURNING id
    """,
        (name, email, password_hash),
    ).fetchone()
    return new_user["id"]


def main():
    # Устанавливаются стандартной командой pip install -r requirements.txt.
    import psycopg
    from werkzeug.security import generate_password_hash

    from fleet.database import connect

    print("Первоначальная настройка администратора ECHO-UNIT")
    print("Эта команда запускается только на компьютере с доступом к PostgreSQL.")
    name = input("Имя администратора: ").strip()
    email = input("Email: ").strip().lower()
    if not 2 <= len(name) <= 80:
        print("Ошибка: имя должно содержать 2–80 символов.")
        return 1
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}", email):
        print("Ошибка: укажите корректный email.")
        return 1
    password = getpass("Пароль (10–128 символов): ")
    confirm = getpass("Повторите пароль: ")
    if not 10 <= len(password) <= 128:
        print("Ошибка: пароль должен содержать 10–128 символов.")
        return 1
    if password != confirm:
        print("Ошибка: пароли не совпадают.")
        return 1
    try:
        with connect() as conn:
            user_id = create_first_admin(
                conn, name, email, generate_password_hash(password)
            )
    except AlreadyConfiguredError as error:
        print(error)
        return 1
    except psycopg.errors.UniqueViolation:
        print("Этот email уже используется. Команда не меняет существующие аккаунты.")
        return 1
    except psycopg.Error:
        print(
            "Ошибка подключения или структуры PostgreSQL. "
            "Проверьте настройки .env и выполните python check_setup.py. "
            "SQL установки применяйте только к новой пустой базе."
        )
        return 1
    print(f"Первый администратор создан, ID: {user_id}. Теперь можно войти в сайт.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
