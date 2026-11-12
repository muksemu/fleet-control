"""Изменение прав в одной транзакции под общей блокировкой администраторов."""

import logging

from werkzeug.security import check_password_hash

from .. import database as db
from ..errors import APIError
from ..user_roles import ADMIN_LOCK_KEY, would_remove_last_admin

logger = logging.getLogger("fleet")


def current_admin_for_change(conn, actor_id):
    """Перепроверяем роль из БД прямо перед изменением прав, не доверяя старой сессии."""
    actor = conn.execute(
        """
        SELECT id, role, active, password_hash
        FROM fleet_users WHERE id = %s FOR UPDATE
    """,
        (actor_id,),
    ).fetchone()
    return actor if actor and actor["role"] == "admin" and actor["active"] else None


def active_admin_count(conn):
    result = conn.execute("""
        SELECT COUNT(*) AS count FROM fleet_users
        WHERE role = 'admin' AND active = TRUE
    """).fetchone()
    return result["count"]


def change_role(actor_id: int, user_id: int, new_role: str, password: str):
    with db.connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (ADMIN_LOCK_KEY,))
        actor = current_admin_for_change(conn, actor_id)
        if not actor:
            raise APIError("Права администратора больше не действуют", 403)
        if not check_password_hash(actor["password_hash"], password):
            raise APIError("Неверный пароль администратора", 403)
        target = conn.execute(
            """
            SELECT id, name, role, active FROM fleet_users
            WHERE id = %s FOR UPDATE
        """,
            (user_id,),
        ).fetchone()
        if not target:
            raise APIError("Сотрудник не найден", 404)
        if user_id == actor["id"]:
            raise APIError("Собственную роль нельзя изменить", 409)
        if target["role"] == new_role:
            return {"id": user_id, "role": new_role}
        if new_role == "admin" and not target["active"]:
            raise APIError("Сначала включите аккаунт сотрудника", 409)
        if would_remove_last_admin(
            target, new_role, target["active"], active_admin_count(conn)
        ):
            raise APIError(
                "Нельзя лишить систему последнего активного администратора", 409
            )
        conn.execute(
            "UPDATE fleet_users SET role = %s WHERE id = %s", (new_role, user_id)
        )
    logger.info(
        "Администратор id=%s изменил роль пользователя id=%s на %s",
        actor_id,
        user_id,
        new_role,
    )
    return {"id": user_id, "role": new_role}


def change_active(actor_id: int, user_id: int, new_active: bool):
    if user_id == actor_id and not new_active:
        raise APIError("Нельзя отключить собственный аккаунт", 409)
    with db.connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (ADMIN_LOCK_KEY,))
        actor = current_admin_for_change(conn, actor_id)
        if not actor:
            raise APIError("Права администратора больше не действуют", 403)
        target = conn.execute(
            """
            SELECT id, role, active FROM fleet_users WHERE id = %s FOR UPDATE
        """,
            (user_id,),
        ).fetchone()
        if not target:
            raise APIError("Сотрудник не найден", 404)
        if would_remove_last_admin(
            target, target["role"], new_active, active_admin_count(conn)
        ):
            raise APIError("Нельзя отключить последнего активного администратора", 409)
        conn.execute(
            "UPDATE fleet_users SET active = %s WHERE id = %s",
            (new_active, user_id),
        )
    logger.info(
        "Администратор id=%s изменил доступ сотрудника id=%s: %s",
        actor_id,
        user_id,
        new_active,
    )
    return {"ok": True}
