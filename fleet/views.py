"""Общие данные для прежних Jinja2 HTML-шаблонов."""

from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse
from werkzeug.utils import redirect

from config import ROOT

from .security import csrf_token

templates = Jinja2Templates(directory=str(ROOT / "templates"))


def redirect_page(location, status_code=302):
    # Сохраняем тело HTML и Location, входящие в HTTP-контракт.
    response = redirect(location, code=status_code)
    return HTMLResponse(
        response.get_data(as_text=True),
        status_code=status_code,
        headers={"Location": location},
    )


def render_page(request, name, **context):
    return templates.TemplateResponse(
        request=request,
        name=name,
        context={"csrf_token": csrf_token(request), **context},
    )
