"""Сводка, предупреждения и страницы."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from starlette.responses import HTMLResponse

from .. import database as db
from ..alerts import build_alerts
from ..routes import city_choices, schematic_route
from ..security import login_required
from ..statuses import COMPLETED, DRIVING, PLANNED
from ..views import render_page

router = APIRouter(tags=["dashboard"])


@router.get("/", name="dashboard.home", response_class=HTMLResponse)
@router.head("/", include_in_schema=False)
def home(request: Request, user=Depends(login_required)):
    return render_page(
        request, "index_МКО.html", user=user, route_cities=city_choices()
    )


@router.get("/api/dashboard", name="dashboard.dashboard")
@router.head("/api/dashboard", include_in_schema=False)
def dashboard(request: Request, user=Depends(login_required)):
    """Один запрос для начальной загрузки данных всех разделов."""
    with db.connect() as conn:
        trucks = conn.execute(
            "SELECT id, name, status, driver FROM trucks ORDER BY id"
        ).fetchall()
        trips = conn.execute(
            """
            SELECT r.id, r.truck_id, t.name AS truck_name, r.origin,
                   r.destination, r.status, r.departure_at, r.eta_at
            FROM fleet_trips r JOIN trucks t ON r.truck_id = t.id
            ORDER BY CASE r.status WHEN %s THEN 0
                WHEN %s THEN 1 ELSE 2 END, r.id DESC
        """,
            (DRIVING, PLANNED),
        ).fetchall()
        positions = conn.execute("""
            SELECT truck_id, latitude, longitude, recorded_at, source, speed_kmh
            FROM fleet_positions
        """).fetchall()
        events = conn.execute("""
            SELECT e.id, e.truck_id, t.name AS truck_name,
                   e.description, e.created_at
            FROM fleet_events e LEFT JOIN trucks t ON t.id = e.truck_id
            ORDER BY e.created_at DESC, e.id DESC LIMIT 30
        """).fetchall()

    # datetime -> ISO 8601, чтобы JavaScript мог прочитать даты одинаково.
    for row in trips:
        for key in ("departure_at", "eta_at"):
            row[key] = row[key].isoformat() if row[key] else None
    for row in positions:
        row["recorded_at"] = (
            row["recorded_at"].isoformat() if row["recorded_at"] else None
        )
        row["latitude"] = float(row["latitude"])
        row["longitude"] = float(row["longitude"])
        row["speed_kmh"] = (
            float(row["speed_kmh"]) if row["speed_kmh"] is not None else None
        )
    for row in events:
        row["created_at"] = row["created_at"].isoformat()
    alerts = build_alerts(trucks, trips, positions, datetime.now(timezone.utc))
    routes = [
        {"trip_id": trip["id"], "status": trip["status"], "coordinates": route}
        for trip in trips
        if trip["status"] != COMPLETED
        if (route := schematic_route(trip["origin"], trip["destination"]))
    ]
    return {
        "trucks": trucks,
        "trips": trips,
        "positions": positions,
        "events": events,
        "alerts": alerts,
        "routes": routes,
    }
