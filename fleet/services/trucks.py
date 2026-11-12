"""Изменение статуса машины с учётом активного рейса."""

from .. import database as db
from ..errors import APIError
from ..statuses import DRIVING


def change_status(truck_id: int, status: str):
    with db.connect() as conn:
        # Порядок блокировок тот же, что при начале/завершении рейса: машина → рейс.
        truck = conn.execute(
            "SELECT id, name, status, driver FROM trucks WHERE id = %s FOR UPDATE",
            (truck_id,),
        ).fetchone()
        if not truck:
            raise APIError("Машина не найдена", 404)
        active = conn.execute(
            "SELECT 1 FROM fleet_trips WHERE truck_id = %s AND status = %s",
            (truck_id, DRIVING),
        ).fetchone()
        if status == DRIVING and not active:
            raise APIError(
                "Статус «В пути» устанавливается при запуске рейса в разделе «Рейсы»",
                409,
            )
        if status != DRIVING and active:
            raise APIError("Сначала завершите текущий рейс в разделе «Рейсы»", 409)
        if truck["status"] != status:
            truck = conn.execute(
                """
                UPDATE trucks SET status = %s WHERE id = %s
                RETURNING id, name, status, driver
                """,
                (status, truck_id),
            ).fetchone()
            db.add_event(conn, truck_id, f"Статус машины изменён: {truck['status']}")
    return truck
