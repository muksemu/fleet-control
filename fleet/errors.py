"""Общие HTTP-ошибки: ключ error, безопасный ответ БД и HTML 404/405."""

import logging

import psycopg
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse, JSONResponse
from werkzeug.exceptions import default_exceptions

logger = logging.getLogger("fleet")


class APIError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def register_error_handlers(app, routers):
    @app.exception_handler(APIError)
    async def api_error(request, error):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": error.message}, status_code=error.status_code)
        return HTMLResponse(error.message, status_code=error.status_code)

    @app.exception_handler(psycopg.Error)
    async def database_error(request, error):
        # SQL, параметры подключения и пароли не должны попасть в HTTP-ответ.
        logger.error("Ошибка PostgreSQL (%s)", type(error).__name__)
        if error.sqlstate in ("42P01", "42703"):
            message = (
                "Схема PostgreSQL не соответствует приложению. "
                "Проверьте подключённую базу и запустите python check_setup.py. "
                "Скрипт sql/install_new.sql предназначен только для новой пустой базы."
            )
        else:
            message = "Ошибка работы с PostgreSQL"
        return JSONResponse({"error": message}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({"error": "Некорректный запрос"}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        if error.status_code == 302:
            from .views import redirect_page

            return redirect_page(error.headers["Location"], status_code=302)
        if error.status_code == 405 and request.method == "OPTIONS":
            methods = {"OPTIONS"}
            for router in routers:
                for route in router.routes:
                    if route.path_regex.fullmatch(request.url.path):
                        methods.update(route.methods)
            return HTMLResponse("", headers={"Allow": ", ".join(sorted(methods))})
        # Сохраняем HTML ошибок, который уже входит в HTTP-контракт клиентов.
        if error.status_code in default_exceptions:
            return HTMLResponse(
                default_exceptions[error.status_code]().get_body(),
                status_code=error.status_code,
                headers=error.headers,
            )
        return JSONResponse({"error": str(error.detail)}, status_code=error.status_code)
