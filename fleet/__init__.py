"""Собирает FastAPI: маршруты, сессии, ошибки и статические файлы."""


def create_app():
    from fastapi import Depends, FastAPI, Request
    from fastapi.staticfiles import StaticFiles
    from starlette.middleware.sessions import SessionMiddleware

    import config

    from .errors import register_error_handlers
    from .security import prepare_request

    app = FastAPI(
        title="ECHO-UNIT / Fleet Control",
        version="2.0.0",
        description="Учебная локальная диспетчерская. Схематические GPS-маршруты.",
        dependencies=[Depends(prepare_request)],
        redirect_slashes=False,
    )
    app.state.gps_token = config.gps_token()
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.session_secret(),
        session_cookie="session",
        max_age=12 * 60 * 60,
        same_site="lax",
        https_only=config.https_enabled(),
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = (
            "strict-origin-when-cross-origin"
            if request.url.path == "/"
            else "same-origin"
        )
        if request.url.path.startswith("/api/") or request.url.path in (
            "/",
            "/login",
            "/register",
            "/docs",
            "/redoc",
            "/openapi.json",
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    from .routers import account, auth, dashboard, telemetry, trips, trucks, users

    routers = [
        module.router
        for module in (auth, account, users, dashboard, trucks, trips, telemetry)
    ]
    for router in routers:
        app.include_router(router)
    register_error_handlers(app, routers)
    app.mount(
        "/static", StaticFiles(directory=str(config.ROOT / "static")), name="static"
    )

    from .api_docs import configure_docs

    configure_docs(app)
    return app
