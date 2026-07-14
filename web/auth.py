from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
import httpx
import urllib.parse
import os
import json
from config import cfg

router = APIRouter()

DISCORD_API_ENDPOINT = "https://discord.com/api/v10"


@router.get("/auth/login")
async def login():
    params = {
        "client_id": cfg.discord_client_id,
        "redirect_uri": cfg.oauth_redirect_uri,
        "response_type": "code",
        "scope": "identify guilds guilds.members.read connections"
    }
    url = f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)


@router.get("/callback")
async def callback(request: Request, code: str):
    data = {
        "client_id": cfg.discord_client_id,
        "client_secret": cfg.discord_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg.oauth_redirect_uri
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        # 1. Đổi code lấy token
        r = await client.post(f"{DISCORD_API_ENDPOINT}/oauth2/token", data=data, headers=headers)
        if r.status_code != 200:
            return HTMLResponse(f"<h2>Lỗi đăng nhập: {r.text}</h2>", status_code=400)

        token_info = r.json()
        access_token = token_info.get("access_token")
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # 2. Lấy thông tin user
        r_user = await client.get(f"{DISCORD_API_ENDPOINT}/users/@me", headers=auth_headers)
        user_info = r_user.json()

        # 3. Lấy danh sách guild của user
        r_guilds = await client.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=auth_headers)
        user_guilds = r_guilds.json() if r_guilds.status_code == 200 else []

        # 4. Lấy các tài khoản liên kết
        r_conn = await client.get(f"{DISCORD_API_ENDPOINT}/users/@me/connections", headers=auth_headers)
        user_connections = r_conn.json() if r_conn.status_code == 200 else []

    uid = user_info.get("id", "")
    avatar_hash = user_info.get("avatar")
    banner_hash = user_info.get("banner")
    badges = decode_badges(user_info.get("public_flags", 0))

    # 5. Lưu data đầy đủ vào SERVER MEMORY (không vào cookie)
    full_profile = {
        "id": uid,
        "username": user_info.get("username"),
        "global_name": user_info.get("global_name"),
        "avatar": avatar_hash,
        "avatar_url": (
            f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.png"
            if avatar_hash else
            f"https://cdn.discordapp.com/embed/avatars/{int(uid) % 5}.png"
        ),
        "banner_url": (
            f"https://cdn.discordapp.com/banners/{uid}/{banner_hash}.png"
            if banner_hash else None
        ),
        "accent_color": user_info.get("accent_color"),
        "badges": badges,
        "guilds": [
            {
                "id": g.get("id"),
                "name": g.get("name"),
                "icon": g.get("icon"),
                "owner": g.get("owner", False),
                "permissions": g.get("permissions")
            }
            for g in (user_guilds if isinstance(user_guilds, list) else [])
        ],
        "connections": [
            {
                "type": c.get("type"),
                "name": c.get("name"),
                "verified": c.get("verified", False),
                "visibility": c.get("visibility")
            }
            for c in (user_connections if isinstance(user_connections, list) else [])
        ]
    }

    # Lưu vào app.state.user_store (server memory)
    request.app.state.user_store[uid] = full_profile

    # Lưu vĩnh viễn vào data/users.json để tra cứu sau này
    try:
        os.makedirs("data", exist_ok=True)
        users_db = {}
        if os.path.exists("data/users.json"):
            with open("data/users.json", "r", encoding="utf-8") as f:
                users_db = json.load(f)
        users_db[uid] = full_profile
        with open("data/users.json", "w", encoding="utf-8") as f:
            json.dump(users_db, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Lỗi lưu data/users.json: {e}")

    # 6. Cookie chỉ lưu user_id (< 50 bytes, không bao giờ vượt giới hạn)
    request.session["uid"] = uid

    # 7. Kiểm tra quyền admin
    is_admin = any(
        g.get("owner") or (int(g.get("permissions", 0)) & 0x20)
        for g in (user_guilds if isinstance(user_guilds, list) else [])
    )

    dest = "/control" if is_admin else "/profile"

    # Dùng HTML + JS redirect để đảm bảo cookie được lưu trước khi navigate
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Đang đăng nhập...</title>
  <style>
    body {{ margin:0; background:#0f0f1a; display:flex; align-items:center;
           justify-content:center; min-height:100vh; font-family:Inter,sans-serif; color:#fff; }}
    .box {{ text-align:center; }}
    .spinner {{ width:40px; height:40px; border:3px solid rgba(255,255,255,0.1);
               border-top-color:#5865F2; border-radius:50%;
               animation:spin 0.8s linear infinite; margin:0 auto 16px; }}
    @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
  </style>
</head>
<body>
  <div class="box">
    <div class="spinner"></div>
    <p>Đang đăng nhập, vui lòng đợi...</p>
  </div>
  <script>
    setTimeout(function() {{ window.location.href = "{dest}"; }}, 400);
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


def decode_badges(flags: int) -> list[str]:
    badge_map = {
        1: "Discord Staff", 2: "Discord Partner", 4: "HypeSquad Events",
        8: "Bug Hunter Lv.1", 64: "HypeSquad Bravery", 128: "HypeSquad Brilliance",
        256: "HypeSquad Balance", 512: "Early Supporter", 16384: "Bug Hunter Lv.2",
        131072: "Verified Bot Developer", 4194304: "Active Developer",
    }
    return [name for bit, name in badge_map.items() if flags & bit]


@router.get("/auth/logout")
async def logout(request: Request):
    uid = request.session.get("uid")
    if uid and uid in request.app.state.user_store:
        del request.app.state.user_store[uid]
    request.session.clear()
    return RedirectResponse("/")
