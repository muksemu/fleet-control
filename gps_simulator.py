"""Учебный GPS-симулятор для нескольких грузовиков ECHO-UNIT.

Читает активные рейсы через API сервера. Двигаются только машины с
активным рейсом и статусом «В пути». Остальные остаются на месте.
Все координаты тестовые; местоположение телефона не используется.
"""

import argparse
import json
import math
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from fleet.routes import schematic_route
from fleet.statuses import DRIVING

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

SERVER = "http://127.0.0.1:8000"


def distance_km(a, b):
    """Расстояние между двумя координатами по прямой в километрах."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371 * 2 * math.asin(min(1.0, math.sqrt(h)))


def route_for_truck(truck):
    """Берём маршрут из активного рейса, не из номера грузовика.

    GPS-симулятор НЕ рисует дорожную сеть: только учебную прямую между городами.
    Для неизвестных городов возвращаем None, а не случайное движение по Москве.
    """
    return schematic_route(truck.get("origin"), truck.get("destination"))


def point_on_globe(start, finish, share):
    """Точка на кратчайшей линии по сфере (не реальный автомобильный маршрут)."""
    lat1, lon1 = map(math.radians, start)
    lat2, lon2 = map(math.radians, finish)
    angular = distance_km(start, finish) / 6371
    if angular < 1e-10:
        return start
    w1 = math.sin((1 - share) * angular) / math.sin(angular)
    w2 = math.sin(share * angular) / math.sin(angular)
    x = w1 * math.cos(lat1) * math.cos(lon1) + w2 * math.cos(lat2) * math.cos(lon2)
    y = w1 * math.cos(lat1) * math.sin(lon1) + w2 * math.cos(lat2) * math.sin(lon2)
    z = w1 * math.sin(lat1) + w2 * math.sin(lat2)
    return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))


def resume_share(route, truck):
    """Продолжить текущий маршрут после перезапуска без прыжка к старту.

    Учитываем только сохранённую тестовую точку, лежащую около линии рейса.
    Если координаты принадлежат другой поездке, стартуем с начала.
    """
    if truck.get("source") != "simulated":
        return 0.0
    lat, lon = truck.get("latitude"), truck.get("longitude")
    if lat is None or lon is None:
        return 0.0
    start, finish = route[0], route[-1]
    current = (float(lat), float(lon))
    total = distance_km(start, finish)
    if total <= 0:
        return 0.0
    before = distance_km(start, current)
    after = distance_km(current, finish)
    # Для точек на линии: расстояние до старта + до финиша ≈ длине маршрута.
    if abs(before + after - total) > max(1.0, total * 0.01):
        return 0.0
    return min(1.0, before / total)


def one_way_points(route, interval, speed_kmh, time_scale=60, start_share=0.0):
    """Идём от отправления к назначению и останавливаемся там.

    time_scale ускоряет только тестовое движение, показанная скорость — условная.
    """
    if (
        route is None
        or len(route) < 2
        or interval <= 0
        or speed_kmh <= 0
        or time_scale <= 0
    ):
        raise ValueError("Неверные параметры учебного маршрута")
    start, finish = route[0], route[-1]
    total = distance_km(start, finish)
    travelled = total * start_share
    initial = point_on_globe(start, finish, start_share)
    yield (
        round(initial[0], 6),
        round(initial[1], 6),
        (speed_kmh if 0 < start_share < 1 else 0.0),
    )
    while travelled < total:
        travelled = min(total, travelled + speed_kmh * interval * time_scale / 3600)
        factor = travelled / total
        latitude, longitude = point_on_globe(start, finish, factor)
        yield (
            round(latitude, 6),
            round(longitude, 6),
            (speed_kmh if travelled < total else 0.0),
        )
    while True:
        yield round(finish[0], 6), round(finish[1], 6), 0.0


def load_token():
    token = os.getenv("GPS_INGEST_TOKEN")
    if not token:
        token_file = Path(__file__).resolve().parent / ".gps_token"
        if not token_file.is_file():
            raise ValueError("Нет .gps_token. Сначала запустите сервер: python main.py")
        token = token_file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise ValueError("Токен слишком короткий (минимум 32 символа)")
    return token


def get_simulation_state(token, server):
    """Получаем от сервера реальные статусы машин и активные рейсы из БД."""
    request = Request(
        server.rstrip("/") + "/api/telemetry/simulation-state",
        headers={"Authorization": "Bearer " + token},
        method="GET",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))["trucks"]


def send_position(truck_id, latitude, longitude, speed_kmh, token, server):
    payload = json.dumps(
        {
            "truck_id": truck_id,
            "latitude": latitude,
            "longitude": longitude,
            "speed_kmh": speed_kmh,
        }
    ).encode("utf-8")
    request = Request(
        server.rstrip("/") + "/api/telemetry/positions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def next_updates(
    trucks, tracks, interval, speed_kmh, only_truck_id=None, time_scale=60
):
    """Статус рейса определяет движение; неизвестные города не угадываем.

    `tracks` хранит по грузовику (id рейса, название маршрута, генератор).
    Функция не делает HTTP-запросов и легко проверяется тестами.
    """
    updates, states, seen = [], {}, set()
    for truck in trucks:
        truck_id = truck["truck_id"]
        if only_truck_id is not None and truck_id != only_truck_id:
            continue
        seen.add(truck_id)
        active_trip = truck.get("active_trip_id")
        moving = truck["status"] == DRIVING and active_trip is not None
        if moving:
            route = route_for_truck(truck)
            if route is None:
                states[truck_id] = "Нет учебного маршрута для этих городов"
                tracks.pop(truck_id, None)
                continue
            states[truck_id] = "В пути"
            trip_key = (active_trip, truck.get("origin"), truck.get("destination"))
            if truck_id not in tracks or tracks[truck_id][0] != trip_key:
                tracks[truck_id] = (
                    trip_key,
                    one_way_points(
                        route,
                        interval,
                        speed_kmh,
                        time_scale,
                        resume_share(route, truck),
                    ),
                )
            lat, lon, speed = next(tracks[truck_id][1])
            updates.append((truck_id, lat, lon, speed))
        else:
            states[truck_id] = (
                "Нет активного рейса" if truck["status"] == DRIVING else truck["status"]
            )
            tracks.pop(truck_id, None)
            # Уже сохранённую точку не двигаем; можно подтверждать её с нулевой скоростью.
            if truck.get("source") == "simulated" and truck.get("latitude") is not None:
                updates.append(
                    (truck_id, float(truck["latitude"]), float(truck["longitude"]), 0.0)
                )
    for truck_id in list(tracks):
        if truck_id not in seen:
            tracks.pop(truck_id)
    return updates, states


def main():
    parser = argparse.ArgumentParser(
        description="GPS-симуляция по состоянию рейсов в PostgreSQL"
    )
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument(
        "--all", action="store_true", help="Следить за всеми грузовиками"
    )
    choice.add_argument("--truck-id", type=int, help="Следить только за одной машиной")
    parser.add_argument(
        "--interval", type=float, default=5, help="Интервал 1–60 секунд"
    )
    parser.add_argument(
        "--speed", type=float, default=65, help="Условная скорость 1–100 км/ч"
    )
    parser.add_argument(
        "--time-scale", type=int, default=60, help="Ускорение тестового движения 1–120"
    )
    args = parser.parse_args()
    if (
        (args.truck_id is not None and args.truck_id <= 0)
        or not 1 <= args.interval <= 60
        or not 1 <= args.speed <= 100
        or not 1 <= args.time_scale <= 120
    ):
        parser.error("ID > 0, интервал 1–60, скорость 1–100, ускорение 1–120")
    try:
        token = load_token()
    except ValueError as error:
        parser.error(str(error))

    print("GPS-СИМУЛЯЦИЯ. Двигаются только машины с активным рейсом «В пути».")
    print("Начни рейс на сайте, чтобы машина поехала. Заверши — чтобы остановилась.")
    print(
        f"Тестовый маршрут — ПРЯМАЯ между городами, не дорога. Ускорение x{args.time_scale}."
    )
    print("Телефон и сторонние GPS-сервисы не используются. Выход: Ctrl+C.\n")
    tracks = {}
    previous_states = {}
    try:
        while True:
            try:
                trucks = get_simulation_state(token, SERVER)
                if args.truck_id is not None and not any(
                    truck["truck_id"] == args.truck_id for truck in trucks
                ):
                    print(f"Грузовик #{args.truck_id} не найден в базе. Остановка.")
                    break
                updates, states = next_updates(
                    trucks,
                    tracks,
                    args.interval,
                    args.speed,
                    args.truck_id,
                    args.time_scale,
                )
                for truck_id, state in states.items():
                    if previous_states.get(truck_id) != state:
                        print(
                            f"#{truck_id}: {state}"
                            + (
                                " — учебный рейс включён"
                                if state == DRIVING
                                else " — не движется"
                            )
                        )
                previous_states = states

                for truck_id, lat, lon, speed in updates:
                    try:
                        send_position(truck_id, lat, lon, speed, token, SERVER)
                    except HTTPError as error:
                        # Рейс мог закончиться между GET состояния и POST точки.
                        # Следующим циклом перечитаем статус из базы.
                        if error.code == 409:
                            print(f"#{truck_id}: рейс изменился; перечитаем статус")
                            continue
                        raise
                    if speed > 0:
                        print(f"#{truck_id}: {lat:.6f}, {lon:.6f} | {speed:g} км/ч")
            except HTTPError as error:
                details = error.read().decode("utf-8", errors="replace")[:200]
                print(f"Ошибка сервера {error.code}: {details}. Симулятор остановлен.")
                break
            except (
                URLError,
                TimeoutError,
                OSError,
                KeyError,
                TypeError,
                ValueError,
            ) as error:
                print(
                    f"Нет связи или неверный ответ сервера: {error}. Симулятор остановлен."
                )
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nСимулятор остановлен. Координаты сохранены в PostgreSQL.")


if __name__ == "__main__":
    main()
