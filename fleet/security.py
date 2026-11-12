"""Cookie-сессия, свежие права из БД, CSRF и отдельный доступ симулятора."""

import hmac
import json
import secrets

from fastapi import Depends, Request
from starlette.exceptions import HTTPException

from . import database as db
from .errors import APIError

CSRF_ERROR = "Сессия устарела. Обновите страницу и повторите действие."
MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def csrf_token(request):
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    return request.session["csrf_token"]


def load_user(request: Request):
    user = None
    if request.session.get("user_id"):
        with db.connect() as conn:
            user = conn.execute(
                "SELECT id, name, email, created_at, password_hash, role, active FROM fleet_users WHERE id = %s",
                (request.session["user_id"],),
            ).fetchone()
        if user is None or not user["active"]:
            user = None
            request.session.clear()
        else:
            # Срок активной сессии продлевается до 12 часов.
            request.session["user_id"] = user["id"]
    request.state.user = user
    return user


async def prepare_request(request: Request, user=Depends(load_user)):
    """Читаем HTTP-тело один раз. SQL выполняется в sync-зависимости выше."""
    request.state.form = {}
    request.state.payload = None
    if request.method not in MUTATING_METHODS:
        return
    content_type = (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )
    if content_type in ("application/x-www-form-urlencoded", "multipart/form-data"):
        request.state.form = await request.form()
    elif content_type == "application/json" or content_type.endswith("+json"):
        try:
            request.state.payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # Невалидное тело остаётся None; read_body вернёт ошибку 400.

    if request.url.path == "/api/telemetry/positions" and request.method == "POST":
        return
    submitted = request.headers.get("X-CSRF-Token") or request.state.form.get(
        "csrf_token", ""
    )
    expected = request.session.get("csrf_token", "")
    if (
        not isinstance(submitted, str)
        or not submitted
        or not expected
        or not hmac.compare_digest(submitted.encode(), expected.encode())
    ):
        raise APIError(CSRF_ERROR)


def login_required(request: Request, user=Depends(load_user)):
    if user is None:
        if request.url.path.startswith("/api/"):
            raise APIError("Нужно войти в аккаунт", 401)
        raise HTTPException(302, headers={"Location": "/login"})
    return user


def admin_required(user=Depends(login_required)):
    if user["role"] != "admin":
        raise APIError("Это действие доступно только администратору", 403)
    return user


def valid_password(value):
    return isinstance(value, str) and 10 <= len(value) <= 128


def simulator_allowed(request: Request):
    authorization = request.headers.get("Authorization", "")
    return (
        request.client is not None
        and request.client.host in ("127.0.0.1", "::1")
        and authorization.startswith("Bearer ")
        and hmac.compare_digest(
            authorization[7:].encode(), request.app.state.gps_token.encode()
        )
    )
