"""HTTP-адреса рейсов. Проверка JSON → транзакция → прежний JSON-ответ."""

from fastapi import APIRouter, Depends, Request

from ..schemas import TripCreate, TripStatus, json_body, read_body
from ..security import login_required
from ..services import trips

router = APIRouter(tags=["trips"])


@router.post(
    "/api/trips",
    status_code=201,
    openapi_extra=json_body(TripCreate),
    responses={404: {"description": "Запись не найдена"}},
)
def create_trip(request: Request, user=Depends(login_required)):
    data = read_body(request, TripCreate)
    return trips.create_trip(data)


@router.patch(
    "/api/trips/{trip_id:int}/status",
    openapi_extra=json_body(TripStatus),
    responses={
        404: {"description": "Запись не найдена"},
        409: {"description": "Действие противоречит текущему состоянию"},
    },
)
def update_trip_status(request: Request, trip_id: int, user=Depends(login_required)):
    data = read_body(request, TripStatus, "Недопустимый статус рейса")
    return trips.change_status(trip_id, data.status)
