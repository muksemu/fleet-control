"""Безопасная проверка структуры PostgreSQL: только SELECT, ничего не меняем."""

# Названия колонок должны совпадать с SQL сервера.
REQUIRED = {
    "trucks": {"id", "name", "status", "driver"},
    "fleet_users": {
        "id",
        "name",
        "email",
        "password_hash",
        "created_at",
        "role",
        "active",
    },
    "fleet_trips": {
        "id",
        "truck_id",
        "origin",
        "destination",
        "status",
        "departure_at",
        "eta_at",
    },
    "fleet_positions": {
        "truck_id",
        "latitude",
        "longitude",
        "recorded_at",
        "source",
        "speed_kmh",
    },
    "fleet_position_history": {
        "id",
        "truck_id",
        "latitude",
        "longitude",
        "recorded_at",
        "source",
        "speed_kmh",
    },
    "fleet_events": {"id", "truck_id", "description", "created_at"},
}


def find_missing(rows):
    """Вернуть недостающие колонки; удобно проверять без подключения к БД."""
    available = {}
    for row in rows:
        available.setdefault(row["table_name"], set()).add(row["column_name"])
    return {
        table: sorted(columns - available.get(table, set()))
        for table, columns in REQUIRED.items()
        if columns - available.get(table, set())
    }


def id_is_automatic(column):
    """SERIAL (nextval) или IDENTITY допустимы; ручной ID — ошибка."""
    if not column:
        return False
    return (
        column.get("is_identity") == "YES"
        or "nextval(" in str(column.get("column_default") or "").lower()
    )


def inspect_next_id(conn):
    """Только SELECT: проверяем, что последовательность не отстала от MAX(id).

    Это снимок состояния, а не резервирование номера. nextval здесь запрещён:
    даже откат транзакции не вернул бы использованный номер.
    """
    from psycopg import sql

    row = conn.execute("""
        SELECT n.nspname AS schema_name, c.relname AS sequence_name,
               s.seqincrement AS step
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_sequence s ON s.seqrelid = c.oid
        WHERE c.oid = pg_get_serial_sequence('public.trucks', 'id')::regclass
    """).fetchone()
    if not row:
        return {
            "ok": False,
            "reason": "Не найдена связанная последовательность trucks.id",
        }
    state = conn.execute(
        sql.SQL("SELECT last_value, is_called FROM {}.{}").format(
            sql.Identifier(row["schema_name"]), sql.Identifier(row["sequence_name"])
        )
    ).fetchone()
    maximum = conn.execute(
        "SELECT COALESCE(MAX(id), 0) AS maximum FROM public.trucks"
    ).fetchone()["maximum"]
    candidate = state["last_value"] + (row["step"] if state["is_called"] else 0)
    ok = row["step"] > 0 and candidate > maximum
    return {
        "ok": ok,
        "maximum": maximum,
        "next_id": candidate,
        "reason": "" if ok else "Последовательность отстала от существующих ID",
    }


def main():
    from fleet.database import connect

    with connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        rows = conn.execute(
            """
            SELECT table_name, column_name, column_default, is_identity
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ANY(%s)
        """,
            (list(REQUIRED),),
        ).fetchall()
        truck_id = next(
            (
                r
                for r in rows
                if r["table_name"] == "trucks" and r["column_name"] == "id"
            ),
            None,
        )
        automatic_id = id_is_automatic(truck_id)
        id_state = inspect_next_id(conn) if automatic_id else {"ok": False}
    missing = find_missing(rows)
    for table in REQUIRED:
        print(f"{'НЕТ' if table in missing else 'OK '}  {table}")
        if table in missing:
            print("    Не хватает: " + ", ".join(missing[table]))

    print(f"{'OK ' if automatic_id else 'НЕТ'}  автоматический ID грузовика")
    if not automatic_id:
        print("    PostgreSQL должен выдавать ID сам (SERIAL или IDENTITY).")
    elif not id_state["ok"]:
        print("НЕТ  следующий ID: " + id_state["reason"])
    else:
        print(
            f"OK   следующий ID {id_state['next_id']} больше максимального {id_state['maximum']}"
        )

    if missing or not automatic_id or not id_state["ok"]:
        print(
            "\nПроверьте, что подключена нужная база, и сделайте резервную "
            "копию перед исправлениями. sql/install_new.sql предназначен "
            "только для новой пустой базы. Существующую базу он не обновляет."
        )
        raise SystemExit(1)
    print(
        "\nСтруктура таблиц соответствует приложению. Действия сайта проверяйте отдельно."
    )


if __name__ == "__main__":
    import psycopg

    try:
        main()
    except psycopg.Error:
        print(
            "Не удалось проверить PostgreSQL. Проверьте подключение, права SELECT и схему БД."
        )
        raise SystemExit(1)
