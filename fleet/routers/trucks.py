"""Работа с автопарком."""

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from .. import database as db
from ..schemas import TruckCreate, TruckStatus, json_body, read_body
from ..security import admin_required, login_required
from ..services import trucks
from ..statuses import PARKED

router = APIRouter(tags=["trucks"])


@router.get("/api/trucks", name="trucks.get_trucks")
@router.head("/api/trucks", include_in_schema=False)
def get_trucks(request: Request, user=Depends(login_required)):
    with db.connect() as conn:
        trucks = conn.execute(
            "SELECT id, name, status, driver FROM trucks ORDER BY id"
        ).fetchall()
    return trucks


@router.post("/api/trucks", status_code=201, openapi_extra=json_body(TruckCreate))
def create_truck(request: Request, user=Depends(admin_required)):
    """Администратор добавляет машину; ID выдаёт сама база."""
    data = read_body(request, TruckCreate)
    name, driver = data.name, data.driver
    with db.connect() as conn:
        truck = conn.execute(
            """
            INSERT INTO trucks (name, status, driver)
            VALUES (%s, %s, %s)
            RETURNING id, name, status, driver
        """,
            (name, PARKED, driver),
        ).fetchone()
        db.add_event(conn, truck["id"], "Машина добавлена в автопарк")
    return JSONResponse(truck, status_code=201)


@router.patch(
    "/api/trucks/{truck_id:int}/status",
    openapi_extra=json_body(TruckStatus),
    responses={
        404: {"description": "Запись не найдена"},
        409: {"description": "Действие противоречит текущему состоянию"},
    },
)
def update_truck_status(request: Request, truck_id: int, user=Depends(login_required)):
    status = read_body(request, TruckStatus, "Выберите допустимый статус машины").status

    return trucks.change_status(truck_id, status)
