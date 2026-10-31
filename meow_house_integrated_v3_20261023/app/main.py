"""FastAPI entrypoint and owner-facing Jinja dashboard pages."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.api import activities, admin, alerts, auth, boarding, care, ingest, monitor, pets
from app.api.dependencies import require_roles, require_user
from app.config import BASE_DIR, settings
from app.database import init_db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Meow一下 API",
    description="智慧貓屋 AI 活動記錄 Prototype；不提供醫療診斷。",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")

app.include_router(auth.router)
app.include_router(ingest.router)
private_api_dependencies = [Depends(require_user)]
app.include_router(activities.router, dependencies=private_api_dependencies)
app.include_router(alerts.router, dependencies=private_api_dependencies)
app.include_router(boarding.router, dependencies=private_api_dependencies)
app.include_router(care.router, dependencies=private_api_dependencies)
app.include_router(monitor.router, dependencies=private_api_dependencies)
app.include_router(pets.router, dependencies=private_api_dependencies)
app.include_router(admin.router, dependencies=private_api_dependencies)


def _signed_in(request: Request) -> bool:
    return bool(request.session.get("user_id"))


def _context(request: Request, page: str) -> dict:
    role = request.session.get("role", "OWNER")
    role_labels = {"OWNER": "飼主", "CAREGIVER": "照護人員", "ADMIN": "系統管理員"}
    return {
        "request": request,
        "page": page,
        "member_name": request.session.get("name", "小花"),
        "role": role,
        "role_label": role_labels.get(role, role),
    }


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if _signed_in(request):
        return RedirectResponse("/", status_code=303)
    error = request.session.pop("login_error", None)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": error},
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if not _signed_in(request):
        return RedirectResponse("/login", status_code=303)
    role = request.session.get("role")
    template = {"CAREGIVER": "caregiver.html", "ADMIN": "admin.html"}.get(role, "dashboard.html")
    page = {"CAREGIVER": "caregiver", "ADMIN": "admin"}.get(role, "dashboard")
    return templates.TemplateResponse(request=request, name=template, context=_context(request, page))


@app.get("/caregiver", response_class=HTMLResponse)
def caregiver_page(request: Request, _member: dict = Depends(require_roles("CAREGIVER"))):
    return templates.TemplateResponse(request=request, name="caregiver.html", context=_context(request, "caregiver"))


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, _member: dict = Depends(require_roles("ADMIN"))):
    return templates.TemplateResponse(request=request, name="admin.html", context=_context(request, "admin"))


@app.get("/pet", response_class=HTMLResponse)
def pet_page(request: Request, _member: dict = Depends(require_user)):
    return templates.TemplateResponse(request=request, name="pet.html", context=_context(request, "pet"))


@app.get("/activities", response_class=HTMLResponse)
def activities_page(request: Request):
    if not _signed_in(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request=request, name="activities.html", context=_context(request, "activities"))


@app.get("/analysis", response_class=HTMLResponse)
def analysis_page(request: Request):
    if not _signed_in(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request=request, name="analysis.html", context=_context(request, "analysis"))


@app.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request):
    if not _signed_in(request):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request=request, name="alerts.html", context=_context(request, "alerts"))


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}
