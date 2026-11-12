"""Последняя точка и история GPS в одной транзакции."""

from .. import database as db
from ..errors import APIError
from ..statuses import DRIVING


def save_position(conn, truck_id, latitude, longitude, speed_kmh, source):
    """Последняя точка + история: оба SQL-запроса в одной транзакции."""
    previous = conn.execute(
        """
        SELECT latitude, longitude, speed_kmh, source
        FROM fleet_positions WHERE truck_id = %s FOR UPDATE
    """,
        (truck_id,),
    ).fetchone()
    # Одинаковые неподвижные точки обновляют время последнего сигнала,
    # но не заполняют историю тысячами повторяющихся записей.
    changed = (
        previous is None
        or previous["source"] != source
        or round(float(previous["latitude"]), 6) != round(latitude, 6)
        or round(float(previous["longitude"]), 6) != round(longitude, 6)
        or (float(previous["speed_kmh"]) if previous["speed_kmh"] is not None else None)
        != (round(speed_kmh, 1) if speed_kmh is not None else None)
    )
    conn.execute(
        """
        INSERT INTO fleet_positions
            (truck_id, latitude, longitude, speed_kmh, source, recorded_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (truck_id) DO UPDATE SET
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            speed_kmh = EXCLUDED.speed_kmh,
            source = EXCLUDED.source,
            recorded_at = EXCLUDED.recorded_at
    """,
        (truck_id, latitude, longitude, speed_kmh, source),
    )
    if changed:
        conn.execute(
            """
            INSERT INTO fleet_position_history
                (truck_id, latitude, longitude, speed_kmh, source)
            VALUES (%s, %s, %s, %s, %s)
        """,
            (truck_id, latitude, longitude, speed_kmh, source),
        )


def receive_position(data):
    with db.connect() as conn:
        truck = conn.execute(
            "SELECT id, status FROM trucks WHERE id = %s FOR UPDATE", (data.truck_id,)
        ).fetchone()
        if not truck:
            raise APIError(f"Грузовик #{data.truck_id} не найден в базе", 404)
        active_trip = conn.execute(
            """
            SELECT id FROM fleet_trips
            WHERE truck_id = %s AND status = %s
        """,
            (data.truck_id, DRIVING),
        ).fetchone()
        if data.speed_kmh > 0 and (truck["status"] != DRIVING or not active_trip):
            raise APIError("Нельзя двигать машину без активного рейса", 409)
        save_position(
            conn,
            data.truck_id,
            data.latitude,
            data.longitude,
            data.speed_kmh,
            "simulated",
        )
    return {"ok": True, "truck_id": data.truck_id}
