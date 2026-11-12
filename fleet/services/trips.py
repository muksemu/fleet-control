"""Транзакции рейсов. Машина и рейс всегда изменяются вместе."""

from .. import database as db
from ..errors import APIError
from ..routes import schematic_route
from ..statuses import DRIVING, PARKED, REPAIR, TRIP_TRANSITIONS


def create_trip(data):
    with db.connect() as conn:
        truck = conn.execute(
            "SELECT id, status FROM trucks WHERE id = %s FOR UPDATE", (data.truck_id,)
        ).fetchone()
        if not truck:
            raise APIError("Машина не найдена", 404)
        if truck["status"] == REPAIR:
            raise APIError("Нельзя назначить рейс машине на ремонте")
        trip = conn.execute(
            """
            INSERT INTO fleet_trips (truck_id, origin, destination, eta_at)
            VALUES (%s, %s, %s, %s) RETURNING id
        """,
            (data.truck_id, data.origin, data.destination, data.eta_at),
        ).fetchone()
        db.add_event(
            conn,
            data.truck_id,
            f"Создан рейс #{trip['id']}: {data.origin} → {data.destination}",
        )
    return {"id": trip["id"]}


def change_status(trip_id, next_status):
    with db.connect() as conn:
        trip_ref = conn.execute(
            "SELECT truck_id FROM fleet_trips WHERE id = %s", (trip_id,)
        ).fetchone()
        if not trip_ref:
            raise APIError("Рейс не найден", 404)
        # Всегда машина → рейс. Такой же порядок используется в GPS и автопарке.
        truck = conn.execute(
            "SELECT status FROM trucks WHERE id = %s FOR UPDATE",
            (trip_ref["truck_id"],),
        ).fetchone()
        trip = conn.execute(
            "SELECT truck_id, status, origin, destination FROM fleet_trips WHERE id = %s FOR UPDATE",
            (trip_id,),
        ).fetchone()
        if not trip:
            raise APIError("Рейс не найден", 404)
        if next_status == trip["status"]:
            return {"ok": True}
        if TRIP_TRANSITIONS.get(trip["status"]) != next_status:
            raise APIError("Сначала начните рейс, затем завершите его")
        if next_status == DRIVING:
            if schematic_route(trip["origin"], trip["destination"]) is None:
                raise APIError(
                    "Для этого рейса нет учебного маршрута. Выберите поддерживаемые города.",
                    409,
                )
            if truck["status"] == REPAIR:
                raise APIError("Машина находится на ремонте")
            busy = conn.execute(
                """
                SELECT 1 FROM fleet_trips
                WHERE truck_id = %s AND status = %s AND id <> %s
            """,
                (trip["truck_id"], DRIVING, trip_id),
            ).fetchone()
            if busy:
                raise APIError("Машина уже выполняет другой рейс", 409)
        if next_status == DRIVING:
            conn.execute(
                """
                DELETE FROM fleet_positions
                WHERE truck_id = %s AND source = 'simulated'
                """,
                (trip["truck_id"],),
            )
        conn.execute(
            "UPDATE fleet_trips SET status = %s WHERE id = %s", (next_status, trip_id)
        )
        truck_status = DRIVING if next_status == DRIVING else PARKED
        conn.execute(
            "UPDATE trucks SET status = %s WHERE id = %s",
            (truck_status, trip["truck_id"]),
        )
        db.add_event(conn, trip["truck_id"], f"Рейс #{trip_id}: {next_status}")
    return {"ok": True}
