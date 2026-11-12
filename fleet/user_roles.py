"""Правила изменения ролей и общий ключ блокировки."""

ADMIN_LOCK_KEY = 20261112


def would_remove_last_admin(user, new_role, new_active, active_admins):
    """True, если изменение оставит систему без активного администратора."""
    currently_admin = user["role"] == "admin" and user["active"]
    stops_being_admin = new_role != "admin" or not new_active
    return currently_admin and stops_being_admin and active_admins <= 1
