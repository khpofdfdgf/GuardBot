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
        "scope": "identify guilds"
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
        
        # 2. Get user info
        r_user = await client.get(f"{DISCORD_API_ENDPOINT}/users/@me", headers={
            "Authorization": f"Bearer {access_token}"
        })
        user_info = r_user.json()
        
        # 3. Get user guilds
        r_guilds = await client.get(f"{DISCORD_API_ENDPOINT}/users/@me/guilds", headers={
            "Authorization": f"Bearer {access_token}"
        })
        user_guilds = r_guilds.json()
        
        # 4. Save to session
        request.session["discord_user"] = {
            "id": user_info.get("id"),
            "username": user_info.get("username"),
            "avatar": user_info.get("avatar")
        }
        
    return RedirectResponse("/control")

@router.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")
