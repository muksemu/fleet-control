"""Проверки реальных состояний БД без побочных эффектов.

Предупреждения рассчитываются из времени ETA и последней телеметрии.
Историю событий они не засоряют: при каждом GET могут исчезнуть/появиться.
"""

from datetime import datetime, timezone

from .routes import schematic_route
from .statuses import DRIVING

GPS_TIMEOUT_SECONDS = 45


def parse_time(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        timestamp = value
    else:
        try:
            timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def build_alerts(trucks, trips, positions, now=None):
    now = now or datetime.now(timezone.utc)
    point_by_truck = {p["truck_id"]: p for p in positions}
    truck_by_id = {t["id"]: t for t in trucks}
    alerts = []
    for trip in trips:
        if trip["status"] != DRIVING:
            continue
        truck_id = trip["truck_id"]
        label = truck_by_id.get(truck_id, {}).get("name", f"Машина #{truck_id}")
        eta = parse_time(trip.get("eta_at"))
        if eta and eta < now:
            alerts.append(
                {
                    "type": "late",
                    "truck_id": truck_id,
                    "trip_id": trip["id"],
                    "message": f"{label}: рейс #{trip['id']} просрочен по плановому времени прибытия",
                }
            )
        if not schematic_route(trip.get("origin"), trip.get("destination")):
            alerts.append(
                {
                    "type": "route",
                    "truck_id": truck_id,
                    "trip_id": trip["id"],
                    "message": f"{label}: для рейса #{trip['id']} нет учебного маршрута между городами",
                }
            )
            continue
        pos = point_by_truck.get(truck_id)
        stamp = parse_time(pos.get("recorded_at")) if pos else None
        if (
            not pos
            or pos.get("source") != "simulated"
            or not stamp
            or (now - stamp).total_seconds() > GPS_TIMEOUT_SECONDS
        ):
            alerts.append(
                {
                    "type": "gps",
                    "truck_id": truck_id,
                    "trip_id": trip["id"],
                    "message": f"{label}: нет свежих данных GPS-симулятора",
                }
            )
    return alerts
