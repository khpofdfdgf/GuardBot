from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os

from config import cfg

# Create directories if they don't exist
os.makedirs("web/static", exist_ok=True)
os.makedirs("web/templates", exist_ok=True)

app = FastAPI(title="Discord Bot Dashboard")

# Thêm SessionMiddleware để hỗ trợ lưu session
app.add_middleware(SessionMiddleware, secret_key=cfg.jwt_secret)

# Global variables to hold bot state
app.state.bot = None

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Setup Jinja2 templates
templates = Jinja2Templates(directory="web/templates")

# Import routers later to avoid circular imports if they rely on app
from web.auth import router as auth_router
from web.api import router as api_router
from web.websockets import router as ws_router

app.include_router(auth_router)
app.include_router(api_router)
app.include_router(ws_router)

@app.get("/")
async def index(request: Request):
    user_session = request.session.get("discord_user")
    if user_session:
        return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user_session})
    else:
        return templates.TemplateResponse(request=request, name="login.html", context={})

@app.get("/tracking")
async def tracking(request: Request):
    user_session = request.session.get("discord_user")
    return templates.TemplateResponse(request=request, name="tracking.html", context={"user": user_session})

@app.get("/control")
async def control(request: Request):
    user_session = request.session.get("discord_user")
    if not user_session:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Vui lòng đăng nhập để truy cập Control Panel"})
    
    return templates.TemplateResponse(request=request, name="control.html", context={"user": user_session})
