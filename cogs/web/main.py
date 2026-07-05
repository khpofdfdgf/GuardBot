from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os
import logging

from config import cfg

# =======================
# LOG SETUP
# =======================
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger("dashboard")

# Create directories
os.makedirs("web/static", exist_ok=True)
os.makedirs("web/templates", exist_ok=True)

app = FastAPI(title="Discord Bot Dashboard")

# =======================
# SESSION
# =======================
app.add_middleware(SessionMiddleware, secret_key=cfg.jwt_secret)

app.state.bot = None

app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

from web.auth import router as auth_router
from web.api import router as api_router

app.include_router(auth_router)
app.include_router(api_router)


# =======================
# ROUTES WITH LOGS
# =======================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.debug(f"➡️ REQUEST: {request.method} {request.url}")
    logger.debug(f"Headers: {dict(request.headers)}")

    response = await call_next(request)

    logger.debug(f"⬅️ RESPONSE STATUS: {response.status_code}")
    return response


@app.get("/")
async def index(request: Request):
    user_session = request.session.get("discord_user")

    logger.debug(f"SESSION DATA: {request.session}")

    if user_session:
        logger.debug(f"USER FOUND: {user_session['username']}")
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"user": user_session}
        )
    else:
        logger.debug("NO SESSION → LOGIN PAGE")
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={}
        )


@app.get("/tracking")
async def tracking(request: Request):
    user_session = request.session.get("discord_user")
    logger.debug(f"TRACKING SESSION: {user_session}")

    return templates.TemplateResponse(
        request=request,
        name="tracking.html",
        context={"user": user_session}
    )


@app.get("/control")
async def control(request: Request):
    user_session = request.session.get("discord_user")

    logger.debug(f"CONTROL ACCESS ATTEMPT: {user_session}")

    if not user_session:
        logger.warning("UNAUTHORIZED ACCESS TO /control")
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Need login"}
        )

    logger.info(f"CONTROL ACCESS GRANTED: {user_session['username']}")

    return templates.TemplateResponse(
        request=request,
        name="control.html",
        context={"user": user_session}
    )