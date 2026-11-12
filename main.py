"""Один сервер FastAPI. Запуск на Mac: python main.py."""

import uvicorn

from fleet import create_app
from fleet.database import get_db_password

app = create_app()

if __name__ == "__main__":
    get_db_password()
    uvicorn.run(app, host="127.0.0.1", port=8000, proxy_headers=False)
