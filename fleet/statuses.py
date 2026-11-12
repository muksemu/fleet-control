"""Серверные названия статусов и разрешённые переходы рейса.

Ограничения CHECK в SQL защищают те же значения на уровне PostgreSQL.
При добавлении статуса их меняют отдельной миграцией, а не при старте сервера.
"""

DRIVING = "В пути"
PARKED = "На месте"
REPAIR = "На ремонте"
PLANNED = "Запланирован"
COMPLETED = "Завершён"

TRUCK_STATUSES = (DRIVING, PARKED, REPAIR)
TRIP_STATUSES = (PLANNED, DRIVING, COMPLETED)
TRIP_TRANSITIONS = {PLANNED: DRIVING, DRIVING: COMPLETED}
