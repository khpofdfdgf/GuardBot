from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
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
# same_site="lax" cho phép cookie sau OAuth2 redirect từ discord.com
# KHÔNG dùng https_only=True vì server chạy HTTP nội bộ (Cloudflare lo HTTPS bên ngoài)
app.add_middleware(
    SessionMiddleware,
    secret_key=cfg.jwt_secret,
    same_site="lax",
    max_age=86400  # Cookie sống 1 ngày
)

# Global variables to hold bot state
app.state.bot = None
# Server-side user data store (key = user_id, value = full profile dict)
# Cookie chỉ chứa user_id nhỏ gọn, data đầy đủ lưu ở đây
app.state.user_store = {}

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
from web.terminal import router as terminal_router

app.include_router(auth_router)
app.include_router(api_router)
app.include_router(ws_router)
app.include_router(terminal_router)

def get_invite_url(request: Request):
    bot = request.app.state.bot
    if bot and bot.user:
        return f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot%20applications.commands"
    return "#"

def get_user(request: Request):
    """Lấy thông tin user từ server-side store."""
    uid = request.session.get("uid")
    if not uid:
        return None
    return request.app.state.user_store.get(uid)

@app.get("/")
async def index(request: Request):
    user = get_user(request)
    invite_url = get_invite_url(request)
    if user:
        return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user, "invite_url": invite_url})
    else:
        return templates.TemplateResponse(request=request, name="login.html", context={"invite_url": invite_url})

@app.get("/tracking")
async def tracking(request: Request):
    user = get_user(request)
    invite_url = get_invite_url(request)
    return templates.TemplateResponse(request=request, name="tracking.html", context={"user": user, "invite_url": invite_url})

@app.get("/control")
async def control(request: Request):
    user = get_user(request)
    invite_url = get_invite_url(request)
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Vui lòng đăng nhập để truy cập Control Panel", "invite_url": invite_url})
    return templates.TemplateResponse(request=request, name="control.html", context={"user": user, "invite_url": invite_url})

@app.get("/lookup")
async def public_lookup_page(request: Request):
    user = get_user(request)
    invite_url = get_invite_url(request)
    return templates.TemplateResponse(request=request, name="lookup.html", context={"user": user, "invite_url": invite_url})

async def is_user_verified(request: Request, user_id: str) -> bool:
    bot = request.app.state.bot
    if not bot:
        return False

    # Nếu chưa cấu hình guild_id hoặc verified_role_id thì mặc định coi như đã xác minh (bypass)
    if not cfg.guild_id or not cfg.verified_role_id:
        return True

    guild = bot.get_guild(cfg.guild_id)
    if not guild:
        try:
            guild = await bot.fetch_guild(cfg.guild_id)
        except Exception:
            return False  # Có cấu hình nhưng bot chưa truy cập được server

    try:
        member = guild.get_member(int(user_id))
        if not member:
            member = await guild.fetch_member(int(user_id))
    except Exception:
        return False  # Không tìm thấy thành viên trong server (chưa tham gia)

    if not member:
        return False

    return any(role.id == cfg.verified_role_id for role in member.roles)

@app.get("/profile")
async def profile_page(request: Request):
    user = get_user(request)
    invite_url = get_invite_url(request)
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context={"invite_url": invite_url, "error": "Vui lòng đăng nhập để xem trang cá nhân"})
    
    if not await is_user_verified(request, user["id"]):
        return RedirectResponse("/verify")
        
    return templates.TemplateResponse(request=request, name="profile.html", context={"user": user, "invite_url": invite_url})

@app.get("/terminal")
async def terminal_panel(request: Request):
    # 1. Kiểm tra session user xem đã đăng nhập qua Discord chưa
    user = get_user(request)
    invite_url = get_invite_url(request)
    
    if not user:
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"error": "Vui lòng đăng nhập để truy cập Web Terminal", "invite_url": invite_url}
        )
    
    # 2. LỚP BẢO MẬT NÂNG CAO: Kiểm tra quyền Admin/Verified trên Server Discord
    # Ngăn chặn user thường mò URL để chiếm quyền điều khiển VPS
    if not await is_user_verified(request, user["id"]):
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"error": "Tài khoản của bạn không có quyền truy cập khu vực kỹ thuật!", "invite_url": invite_url}
        )
    
    # 3. Nếu vượt qua tất cả, render trực tiếp file giao diện terminal độc lập
    return templates.TemplateResponse(
        request=request, 
        name="terminal.html", 
        context={"user": user, "invite_url": invite_url}
    )
@app.get("/verify")
async def verify_page(request: Request):
    user = get_user(request)
    invite_url = get_invite_url(request)
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context={"invite_url": invite_url, "error": "Vui lòng đăng nhập trước khi xác minh"})
    
    if await is_user_verified(request, user["id"]):
        return RedirectResponse("/profile")
        
    # Get server invite link from config if available (rules_channel or custom)
    server_invite = "https://discord.gg/invite"  # Fallback
    bot = request.app.state.bot
    if bot:
        guild = bot.get_guild(cfg.guild_id)
        if guild:
            # Try to get first active invite
            try:
                invites = await guild.invites()
                if invites:
                    server_invite = invites[0].url
            except:
                pass
                
    return templates.TemplateResponse(request=request, name="verify.html", context={
        "user": user, 
        "invite_url": invite_url,
        "server_invite": server_invite
    })

@app.get("/appeals")
async def appeals_page(request: Request):
    user = get_user(request)
    invite_url = get_invite_url(request)
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context={"invite_url": invite_url, "error": "Vui lòng đăng nhập để xem trang kháng cáo"})
    
    # Check if user is admin in any server
    is_admin = any(
        g.get("owner") or (int(g.get("permissions", 0)) & 0x20)
        for g in user.get("guilds", [])
    )
    
    return templates.TemplateResponse(request=request, name="appeals.html", context={
        "user": user,
        "invite_url": invite_url,
        "is_admin": is_admin
    })





