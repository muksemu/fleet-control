"""Приём тестовых GPS-координат и их сохранение."""

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from .. import database as db
from ..schemas import GPSPosition, json_body, read_body
from ..security import simulator_allowed
from ..services.gps import receive_position
from ..statuses import DRIVING

router = APIRouter(tags=["telemetry"])


@router.get("/api/telemetry/simulation-state", name="telemetry.simulation_state")
@router.head("/api/telemetry/simulation-state", include_in_schema=False)
def simulation_state(request: Request):
    """Статусы из PostgreSQL для симулятора, а не из выдуманного списка Python."""
    if not simulator_allowed(request):
        return JSONResponse({"error": "Доступ к симулятору запрещён"}, status_code=403)
    with db.connect() as conn:
        trucks = conn.execute(
            """
            SELECT t.id AS truck_id, t.status,
                   r.id AS active_trip_id, r.origin, r.destination,
                   p.latitude, p.longitude, p.speed_kmh, p.source
            FROM trucks t
            LEFT JOIN fleet_trips r
                ON r.truck_id = t.id AND r.status = %s
            LEFT JOIN fleet_positions p ON p.truck_id = t.id
            ORDER BY t.id
        """,
            (DRIVING,),
        ).fetchall()
    for truck in trucks:
        for field in ("latitude", "longitude", "speed_kmh"):
            if truck[field] is not None:
                truck[field] = float(truck[field])
    return {"trucks": trucks}


@router.post(
    "/api/telemetry/positions",
    status_code=201,
    openapi_extra=json_body(GPSPosition),
    responses={
        404: {"description": "Запись не найдена"},
        409: {"description": "Действие противоречит текущему состоянию"},
    },
)
def receive_telemetry(request: Request):
    """Локальный GPS-симулятор присылает JSON с координатами.

    Здесь НЕТ сессии пользователя. Допуск: localhost и отдельный секрет.
    Важно: не публиковать этот endpoint для внешних устройств как есть.
    """
    if (request.client.host if request.client else "") not in ("127.0.0.1", "::1"):
        return JSONResponse(
            {"error": "Тестовые координаты принимаются только с этого компьютера"},
            status_code=403,
        )
    if not simulator_allowed(request):
        return JSONResponse({"error": "Неверный токен GPS-симулятора"}, status_code=401)
    data = read_body(request, GPSPosition, "Ожидается JSON с координатами")
    return receive_position(data)
