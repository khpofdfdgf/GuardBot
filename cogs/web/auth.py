from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import httpx
import urllib.parse
import logging

from config import cfg

router = APIRouter()
logger = logging.getLogger("oauth")

DISCORD_API_ENDPOINT = "https://discord.com/api/v10"


@router.get("/auth/login")
async def login():
    logger.debug("LOGIN STARTED")

    params = {
        "client_id": cfg.discord_client_id,
        "redirect_uri": cfg.oauth_redirect_uri,
        "response_type": "code",
        "scope": "identify guilds"
    }

    url = f"https://discord.com/api/oauth2/authorize?{urllib.parse.urlencode(params)}"

    logger.debug(f"REDIRECT URL: {url}")

    return RedirectResponse(url)


@router.get("/callback")
async def callback(request: Request, code: str):
    logger.debug(f"OAUTH CALLBACK RECEIVED: code={code}")

    data = {
        "client_id": cfg.discord_client_id,
        "client_secret": cfg.discord_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg.oauth_redirect_uri
    }

    async with httpx.AsyncClient() as client:

        # =======================
        # TOKEN EXCHANGE
        # =======================
        logger.debug("REQUESTING TOKEN...")

        r = await client.post(
            f"{DISCORD_API_ENDPOINT}/oauth2/token",
            data=data
        )

        logger.debug(f"TOKEN STATUS: {r.status_code}")
        logger.debug(f"TOKEN RESPONSE: {r.text}")

        if r.status_code != 200:
            logger.error("TOKEN FAILED")
            return {"error": "token failed", "raw": r.text}

        token_info = r.json()
        access_token = token_info.get("access_token")

        logger.debug(f"ACCESS TOKEN: {access_token}")


        # =======================
        # USER INFO
        # =======================
        logger.debug("FETCHING USER INFO")

        r_user = await client.get(
            f"{DISCORD_API_ENDPOINT}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        logger.debug(f"/users/@me STATUS: {r_user.status_code}")
        logger.debug(f"/users/@me RESPONSE: {r_user.text}")

        if r_user.status_code != 200:
            logger.error("FAILED USER FETCH")
            return {"error": "user fetch failed"}

        user_info = r_user.json()


        # =======================
        # GUILDS
        # =======================
        logger.debug("FETCHING GUILDS")

        r_guilds = await client.get(
            f"{DISCORD_API_ENDPOINT}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        logger.debug(f"GUILDS STATUS: {r_guilds.status_code}")
        logger.debug(f"GUILDS RESPONSE: {r_guilds.text}")

        user_guilds = r_guilds.json()


        # =======================
        # SESSION SAVE
        # =======================
        request.session["discord_user"] = {
            "id": user_info.get("id"),
            "username": user_info.get("username"),
            "avatar": user_info.get("avatar"),
            "guilds": user_guilds
        }

        logger.info(f"LOGIN SUCCESS: {user_info.get('username')}")

    return RedirectResponse("/control")


@router.get("/auth/logout")
async def logout(request: Request):
    logger.info("LOGOUT REQUEST")
    request.session.clear()
    return RedirectResponse("/")