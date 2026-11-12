"""JSON-модели. Проверки сохраняют сообщения и порядок ошибок старого API."""

import re
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from .errors import APIError
from .routes import canonical_city
from .statuses import TRIP_STATUSES, TRUCK_STATUSES


def invalid(message):
    raise PydanticCustomError("input", message)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_default=True)


class TruckCreate(InputModel):
    name: str = ""
    driver: str = "Не назначен"

    @field_validator("name", "driver", mode="before")
    @classmethod
    def text_field(cls, value, info):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
            invalid(
                "Укажите название машины (1–100 символов)"
                if info.field_name == "name"
                else "Укажите имя водителя (1–100 символов)"
            )
        return value.strip()


class TruckStatus(InputModel):
    status: str = Field(default="", json_schema_extra={"enum": list(TRUCK_STATUSES)})

    @field_validator("status", mode="before")
    @classmethod
    def allowed_status(cls, value):
        if value not in TRUCK_STATUSES:
            invalid("Выберите допустимый статус машины")
        return value


class TripStatus(InputModel):
    status: str = Field(default="", json_schema_extra={"enum": list(TRIP_STATUSES)})

    @field_validator("status", mode="before")
    @classmethod
    def allowed_status(cls, value):
        if value not in TRIP_STATUSES:
            invalid("Недопустимый статус рейса")
        return value


class TripCreate(InputModel):
    truck_id: int
    origin: str
    destination: str
    eta_at: datetime

    @model_validator(mode="before")
    @classmethod
    def compatible_values(cls, data):
        try:
            truck_id = int(data.get("truck_id"))
            origin = str(data.get("origin", "")).strip()
            destination = str(data.get("destination", "")).strip()
            if (
                not origin
                or not destination
                or len(origin) > 100
                or len(destination) > 100
            ):
                raise ValueError()
            eta = datetime.fromisoformat(str(data.get("eta_at", "")))
            if eta.tzinfo is None or eta <= datetime.now(eta.tzinfo):
                raise ValueError()
        except (ValueError, TypeError, OverflowError):
            invalid("Укажите машину, города и корректное время прибытия")
        origin, destination = canonical_city(origin), canonical_city(destination)
        if not origin or not destination:
            invalid(
                "Город пока не поддерживается учебным GPS. Выберите город из подсказок."
            )
        if origin == destination:
            invalid("Отправление и назначение должны быть разными городами")
        return {
            "truck_id": truck_id,
            "origin": origin,
            "destination": destination,
            "eta_at": eta,
        }


class GPSPosition(InputModel):
    truck_id: int = Field(strict=True, gt=0)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    speed_kmh: float = Field(ge=0, le=250, allow_inf_nan=False)

    @model_validator(mode="wrap")
    @classmethod
    def compatible_errors(cls, data, validate):
        """Pydantic проверяет числа; наружу сохраняем порядок и тексты ошибок API."""
        try:
            return validate(data)
        except ValidationError as error:
            errors = error.errors()
            if any(item["loc"] == ("truck_id",) for item in errors):
                invalid("truck_id должен быть положительным целым числом")
            if any(
                item["type"] in ("missing", "float_type", "float_parsing")
                for item in errors
            ):
                invalid("Широта, долгота и скорость должны быть числами")
            invalid("Некорректные координаты или скорость (0–250 км/ч)")


class UserCreate(InputModel):
    name: str = ""
    email: str = ""
    password: str = Field(
        default="", repr=False, json_schema_extra={"format": "password"}
    )

    @field_validator("name", mode="before")
    @classmethod
    def check_name(cls, value):
        if not isinstance(value, str) or not 2 <= len(value.strip()) <= 80:
            invalid("Введите имя сотрудника (2–80 символов)")
        return value.strip()

    @field_validator("email", mode="before")
    @classmethod
    def check_email(cls, value):
        if not isinstance(value, str) or not re.fullmatch(
            r"[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}", value.strip().lower()
        ):
            invalid("Укажите корректный email")
        return value.strip().lower()

    @field_validator("password", mode="before")
    @classmethod
    def check_password(cls, value):
        if not isinstance(value, str) or not 10 <= len(value) <= 128:
            invalid("Пароль от 10 до 128 символов")
        return value


class RoleChange(InputModel):
    role: str = ""
    password: str = Field(
        default="", repr=False, json_schema_extra={"format": "password"}
    )

    @field_validator("role", mode="before")
    @classmethod
    def check_role(cls, value):
        if value not in ("admin", "dispatcher"):
            invalid("Выберите роль: admin или dispatcher")
        return value

    @field_validator("password", mode="before")
    @classmethod
    def check_password(cls, value):
        if not isinstance(value, str) or not value:
            invalid("Подтвердите действие своим паролем")
        return value


class ActiveChange(InputModel):
    active: bool = None

    @field_validator("active", mode="before")
    @classmethod
    def check_active(cls, value):
        if not isinstance(value, bool):
            invalid("Укажите active: true или false")
        return value


class NameChange(InputModel):
    name: str = ""

    @field_validator("name", mode="before")
    @classmethod
    def check_name(cls, value):
        if not isinstance(value, str):
            invalid("Укажите имя текстом")
        if not 2 <= len(value.strip()) <= 80:
            invalid("Имя должно содержать от 2 до 80 символов")
        return value.strip()


def read_body(request, model, message="Ожидается JSON"):
    data = request.state.payload
    if not isinstance(data, dict):
        raise APIError(message)
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise APIError(error.errors()[0]["msg"]) from error


def json_body(model):
    """Описывает в OpenAPI те же поля, которые проверяет read_body."""
    schema = model.model_json_schema()
    required = [
        key
        for key in schema["properties"]
        if not (model is TruckCreate and key == "driver")
    ]
    schema["required"] = required
    for key in required:
        schema["properties"][key].pop("default", None)
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": schema}},
        }
    }
