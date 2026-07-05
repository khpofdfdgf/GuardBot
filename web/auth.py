from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import httpx
import urllib.parse
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
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    async with httpx.AsyncClient() as client:
        # 1. Exchange code for token
        r = await client.post(f"{DISCORD_API_ENDPOINT}/oauth2/token", data=data, headers=headers)
        if r.status_code != 200:
            return {"error": "Failed to get token", "details": r.text}
            
        token_info = r.json()
        access_token = token_info.get("access_token")
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        
        # 2. Get user info (đầy đủ: email flag, public_flags, banner, accent_color...)
        r_user = await client.get(f"{DISCORD_API_ENDPOINT}/users/@me", headers=auth_headers)
        user_info = r_user.json()
        
        # 3. Get user guilds (danh sách TẤT CẢ server của họ)
        r_guilds = await client.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers=auth_headers)
        user_guilds = r_guilds.json() if r_guilds.status_code == 200 else []

        # 4. Get user connections (Steam, Twitch, GitHub, Spotify, Twitter...)
        r_connections = await client.get(f"{DISCORD_API_ENDPOINT}/users/@me/connections", headers=auth_headers)
        user_connections = r_connections.json() if r_connections.status_code == 200 else []

        # 5. Decode public_flags thành danh sách huy hiệu
        public_flags = user_info.get("public_flags", 0)
        badges = decode_badges(public_flags)

        # 6. Save to session
        uid = user_info.get("id")
        avatar_hash = user_info.get("avatar")
        banner_hash = user_info.get("banner")

        request.session["discord_user"] = {
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
        
    return RedirectResponse("/control")

def decode_badges(flags: int) -> list[str]:
    """Giải mã public_flags thành danh sách huy hiệu Discord."""
    badge_map = {
        1:       "Discord Staff",
        2:       "Discord Partner",
        4:       "HypeSquad Events",
        8:       "Bug Hunter Lv.1",
        64:      "HypeSquad Bravery",
        128:     "HypeSquad Brilliance",
        256:     "HypeSquad Balance",
        512:     "Early Supporter",
        16384:   "Bug Hunter Lv.2",
        131072:  "Verified Bot Developer",
        4194304: "Active Developer",
    }
    return [name for bit, name in badge_map.items() if flags & bit]

@router.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")
