"""Дополняет OpenAPI: реальные формы, cookie/CSRF и совместимые ошибки 400."""

from fastapi.openapi.utils import get_openapi


def fields_body(fields, content_type, password_fields=()):
    properties = {field: {"type": "string"} for field in fields}
    for field in password_fields:
        properties[field]["format"] = "password"
    body = {
        "required": True,
        "content": {
            content_type: {
                "schema": {
                    "type": "object",
                    "required": fields,
                    "properties": properties,
                }
            }
        },
    }
    return {"requestBody": body}


def configure_docs(app):
    def openapi():
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )
        schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
        schemes["SessionCookie"] = {"type": "apiKey", "in": "cookie", "name": "session"}
        schemes["GPSBearer"] = {"type": "http", "scheme": "bearer"}
        for path, operations in schema["paths"].items():
            for method, operation in operations.items():
                responses = operation.setdefault("responses", {})
                responses.pop("422", None)
                if method in ("post", "patch"):
                    media = (
                        "application/json" if path.startswith("/api/") else "text/html"
                    )
                    error_schema = (
                        {"type": "object", "properties": {"error": {"type": "string"}}}
                        if media == "application/json"
                        else {"type": "string"}
                    )
                    responses["400"] = {
                        "description": "Некорректные данные или CSRF",
                        "content": {media: {"schema": error_schema}},
                    }
                if path.startswith("/api/"):
                    telemetry = "/telemetry/" in path
                    operation["security"] = [
                        {"GPSBearer" if telemetry else "SessionCookie": []}
                    ]
                    responses["503"] = {"description": "Ошибка PostgreSQL"}
                    if not telemetry:
                        responses["401"] = {
                            "description": "Нужен активный вошедший пользователь"
                        }
                    if (
                        path.startswith("/api/users")
                        or (path == "/api/trucks" and method == "post")
                        or telemetry
                    ):
                        responses["403"] = {
                            "description": "Недостаточно прав или запрещён адрес GPS-клиента"
                        }
                    if telemetry and method == "post":
                        responses["401"] = {"description": "Неверный GPS-токен"}
                    if method in ("post", "patch") and not telemetry:
                        operation.setdefault("parameters", []).append(
                            {
                                "name": "X-CSRF-Token",
                                "in": "header",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        )
                if path == "/logout":
                    operation["security"] = [{"SessionCookie": []}]
                if path.startswith("/api/"):
                    for code, response in responses.items():
                        if int(code) >= 400:
                            response["content"] = {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["error"],
                                        "properties": {"error": {"type": "string"}},
                                    }
                                }
                            }
        app.openapi_schema = schema
        return schema

    app.openapi = openapi
