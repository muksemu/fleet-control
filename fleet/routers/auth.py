"""Вход, регистрация и выход."""

import re

import psycopg
from fastapi import APIRouter, Depends, Request
from starlette.responses import HTMLResponse
from werkzeug.security import check_password_hash, generate_password_hash

from .. import database as db
from ..api_docs import fields_body
from ..security import csrf_token, load_user, login_required, valid_password
from ..views import redirect_page, render_page

router = APIRouter(
    tags=["auth"],
    default_response_class=HTMLResponse,
    responses={302: {"description": "Переход на страницу входа или в приложение"}},
)


@router.get("/register", name="auth.register")
@router.head("/register", include_in_schema=False)
@router.post(
    "/register",
    name="auth.register_post",
    openapi_extra=fields_body(
        ["csrf_token", "email", "password", "name", "confirm_password"],
        "application/x-www-form-urlencoded",
        ["password", "confirm_password"],
    ),
)
def register(request: Request, user=Depends(load_user)):
    """Открытая регистрация = заявка. Роль всегда dispatcher, вход до одобрения закрыт."""
    if user:
        return redirect_page("/", status_code=302)
    error_message = None
    if request.method == "POST":
        name = request.state.form.get("name", "").strip()
        email = request.state.form.get("email", "").strip().lower()
        user_password = request.state.form.get("password", "")
        confirmation = request.state.form.get("confirm_password", "")
        if not (2 <= len(name) <= 80):
            error_message = "Укажите имя длиной от 2 до 80 символов"
        elif not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}", email):
            error_message = "Укажите корректный email"
        elif not valid_password(user_password):
            error_message = "Пароль должен содержать от 10 до 128 символов"
        elif user_password != confirmation:
            error_message = "Пароли не совпадают"
        else:
            try:
                with db.connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO fleet_users (name, email, password_hash, role, active)
                        VALUES (%s, %s, %s, 'dispatcher', FALSE)
                    """,
                        (name, email, generate_password_hash(user_password)),
                    )
            except psycopg.errors.UniqueViolation:
                # Не раскрываем посторонним, какой email уже есть в системе.
                return redirect_page("/login?requested=1", status_code=302)
            return redirect_page("/login?requested=1", status_code=302)
    return render_page(
        request,
        "auth_МКО.html",
        mode="register",
        error=error_message,
        entered_name=request.state.form.get("name", ""),
        entered_email=request.state.form.get("email", ""),
    )


@router.get("/login", name="auth.login")
@router.head("/login", include_in_schema=False)
@router.post(
    "/login",
    name="auth.login_post",
    openapi_extra=fields_body(
        ["csrf_token", "email", "password"],
        "application/x-www-form-urlencoded",
        ["password"],
    ),
)
def login(request: Request, user=Depends(load_user)):
    if user:
        return redirect_page("/", status_code=302)
    error_message = None
    if request.method == "POST":
        email = request.state.form.get("email", "").strip().lower()
        user_password = request.state.form.get("password", "")
        with db.connect() as conn:
            account = conn.execute(
                "SELECT id, password_hash, active FROM fleet_users WHERE email = %s",
                (email,),
            ).fetchone()
        if (
            account
            and account["active"]
            and check_password_hash(account["password_hash"], user_password)
        ):
            request.session.clear()
            request.session["user_id"] = account["id"]
            csrf_token(request)  # Новый токен после входа.
            return redirect_page("/", status_code=302)
        error_message = (
            "Неверный email, пароль или доступ ещё не разрешён администратором"
        )
    return render_page(
        request,
        "auth_МКО.html",
        mode="login",
        error=error_message,
        requested=request.query_params.get("requested") == "1",
        entered_email=request.state.form.get("email", ""),
    )


@router.post(
    "/logout",
    name="auth.logout",
    openapi_extra=fields_body(["csrf_token"], "application/x-www-form-urlencoded"),
)
def logout(request: Request, user=Depends(login_required)):
    request.session.clear()
    return redirect_page("/login", status_code=302)
