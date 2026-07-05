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

# ─── Jinja2 custom globals ────────────────────────────────────────────────────
_CONN_COLORS = {
    "steam": "#1b2838", "twitch": "#9146ff", "youtube": "#ff0000",
    "twitter": "#1da1f2", "github": "#24292e", "spotify": "#1db954",
    "reddit": "#ff4500", "facebook": "#1877f2", "tiktok": "#010101",
    "xbox": "#107c10", "playstation": "#00439c", "battlenet": "#009ae4",
    "epicgames": "#2f2f2f", "leagueoflegends": "#c89b3c", "roblox": "#e42424",
}
_CONN_EMOJIS = {
    "steam": "🎮", "twitch": "📡", "youtube": "▶️", "twitter": "🐦",
    "github": "🐙", "spotify": "🎵", "reddit": "🤖", "facebook": "📘",
    "tiktok": "🎵", "xbox": "🎮", "playstation": "🎮", "battlenet": "⚔️",
    "epicgames": "🕹️", "leagueoflegends": "⚔️", "roblox": "🧱",
}
templates.env.globals["conn_color"] = lambda t: _CONN_COLORS.get(t, "#374151")
templates.env.globals["conn_emoji"] = lambda t: _CONN_EMOJIS.get(t, "🔗")


# Import routers later to avoid circular imports if they rely on app
from web.auth import router as auth_router
from web.api import router as api_router
from web.websockets import router as ws_router

app.include_router(auth_router)
app.include_router(api_router)
app.include_router(ws_router)

def get_invite_url(request: Request):
    bot = request.app.state.bot
    if bot and bot.user:
        return f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot%20applications.commands"
    return "#"

@app.get("/")
async def index(request: Request):
    user_session = request.session.get("discord_user")
    invite_url = get_invite_url(request)
    if user_session:
        return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user_session, "invite_url": invite_url})
    else:
        return templates.TemplateResponse(request=request, name="login.html", context={"invite_url": invite_url})

@app.get("/tracking")
async def tracking(request: Request):
    user_session = request.session.get("discord_user")
    invite_url = get_invite_url(request)
    return templates.TemplateResponse(request=request, name="tracking.html", context={"user": user_session, "invite_url": invite_url})

@app.get("/control")
async def control(request: Request):
    user_session = request.session.get("discord_user")
    invite_url = get_invite_url(request)
    if not user_session:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Vui lòng đăng nhập để truy cập Control Panel", "invite_url": invite_url})
    
    return templates.TemplateResponse(request=request, name="control.html", context={"user": user_session, "invite_url": invite_url})

@app.get("/lookup")
async def public_lookup_page(request: Request):
    user_session = request.session.get("discord_user")
    invite_url = get_invite_url(request)
    return templates.TemplateResponse(request=request, name="lookup.html", context={"user": user_session, "invite_url": invite_url})

@app.get("/profile")
async def profile_page(request: Request):
    user_session = request.session.get("discord_user")
    invite_url = get_invite_url(request)
    if not user_session:
        return templates.TemplateResponse(request=request, name="login.html", context={"invite_url": invite_url, "error": "Vui lòng đăng nhập để xem trang cá nhân"})
    return templates.TemplateResponse(request=request, name="profile.html", context={"user": user_session, "invite_url": invite_url})



