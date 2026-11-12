"""Личный кабинет: профиль и пароль."""

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse
from werkzeug.security import check_password_hash, generate_password_hash

from .. import database as db
from ..api_docs import fields_body
from ..schemas import NameChange, json_body, read_body
from ..security import login_required, valid_password

router = APIRouter(tags=["account"])


@router.get("/api/account", name="account.get_account")
@router.head("/api/account", include_in_schema=False)
def get_account(request: Request, user=Depends(login_required)):
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "created_at": user["created_at"].isoformat(),
    }


@router.patch("/api/account/name", openapi_extra=json_body(NameChange))
def update_account_name(request: Request, user=Depends(login_required)):
    name = read_body(request, NameChange, "Укажите имя").name
    with db.connect() as conn:
        conn.execute(
            "UPDATE fleet_users SET name = %s WHERE id = %s", (name, user["id"])
        )
    return {"name": name}


@router.post(
    "/api/account/password",
    name="account.change_account_password_post",
    openapi_extra=fields_body(
        ["old_password", "new_password"],
        "application/json",
        ["old_password", "new_password"],
    ),
)
def change_account_password(request: Request, user=Depends(login_required)):
    body = request.state.payload
    if not isinstance(body, dict):
        return JSONResponse({"error": "Укажите пароли"}, status_code=400)
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")
    if not isinstance(old_password, str):
        return JSONResponse({"error": "Текущий пароль указан неверно"}, status_code=400)
    if not check_password_hash(user["password_hash"], old_password):
        return JSONResponse({"error": "Текущий пароль указан неверно"}, status_code=400)
    if not valid_password(new_password):
        return JSONResponse(
            {"error": "Новый пароль должен содержать от 10 до 128 символов"},
            status_code=400,
        )
    if new_password == old_password:
        return JSONResponse(
            {"error": "Новый пароль должен отличаться от текущего"}, status_code=400
        )
    with db.connect() as conn:
        conn.execute(
            "UPDATE fleet_users SET password_hash = %s WHERE id = %s",
            (generate_password_hash(new_password), user["id"]),
        )
    return {"ok": True}
