"""Сотрудники, роли и права администратора."""

import psycopg
from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse
from werkzeug.security import generate_password_hash

from .. import database as db
from ..schemas import ActiveChange, RoleChange, UserCreate, json_body, read_body
from ..security import admin_required
from ..services import users

router = APIRouter(tags=["users"])


@router.get("/api/users", name="users.list_users")
@router.head("/api/users", include_in_schema=False)
def list_users(request: Request, user=Depends(admin_required)):
    with db.connect() as conn:
        users = conn.execute("""
            SELECT id, name, email, role, active, created_at
            FROM fleet_users ORDER BY id
        """).fetchall()
    for user in users:
        user["created_at"] = user["created_at"].isoformat()
    return users


@router.post(
    "/api/users",
    status_code=201,
    openapi_extra=json_body(UserCreate),
    responses={409: {"description": "Действие противоречит текущему состоянию"}},
)
def create_user(request: Request, user=Depends(admin_required)):
    data = read_body(request, UserCreate)
    name, email, user_password = data.name, data.email, data.password
    try:
        with db.connect() as conn:
            user = conn.execute(
                """
                INSERT INTO fleet_users (name, email, password_hash, role)
                VALUES (%s, %s, %s, 'dispatcher') RETURNING id
            """,
                (
                    name,
                    email,
                    generate_password_hash(user_password),
                ),
            ).fetchone()
    except psycopg.errors.UniqueViolation:
        return JSONResponse(
            {"error": "Этот email уже зарегистрирован"}, status_code=409
        )
    return JSONResponse({"id": user["id"]}, status_code=201)


@router.patch(
    "/api/users/{user_id:int}/role",
    openapi_extra=json_body(RoleChange),
    responses={
        404: {"description": "Запись не найдена"},
        409: {"description": "Действие противоречит текущему состоянию"},
    },
)
def change_user_role(request: Request, user_id: int, user=Depends(admin_required)):
    data = read_body(request, RoleChange, "Выберите роль: admin или dispatcher")
    return users.change_role(user["id"], user_id, data.role, data.password)


@router.patch(
    "/api/users/{user_id:int}/active",
    openapi_extra=json_body(ActiveChange),
    responses={
        404: {"description": "Запись не найдена"},
        409: {"description": "Действие противоречит текущему состоянию"},
    },
)
def set_user_active(request: Request, user_id: int, user=Depends(admin_required)):
    data = read_body(request, ActiveChange, "Укажите active: true или false")
    return users.change_active(user["id"], user_id, data.active)
