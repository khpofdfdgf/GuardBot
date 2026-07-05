from fastapi import APIRouter, Request, HTTPException
import os
import json
from config import cfg

router = APIRouter()

def check_admin(request: Request):
    user_session = request.session.get("discord_user")
    if not user_session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    bot = request.app.state.bot
    if not bot:
        raise HTTPException(status_code=500, detail="Bot is not running")
        
    uid = int(user_session["id"])
    
    # Simple check: Is the user the owner of ANY guild the bot is in, or do they have admin perms?
    is_admin = False
    for guild in bot.guilds:
        member = guild.get_member(uid)
        if member and (guild.owner_id == uid or member.guild_permissions.administrator):
            is_admin = True
            break
            
    if not is_admin:
        raise HTTPException(status_code=403, detail="Forbidden: You are not an administrator")
    
    return bot

@router.get("/api/stats")
async def get_stats(request: Request):
    bot = request.app.state.bot
    if not bot:
        return {"error": "Bot not connected"}
        
    safemode_cog = bot.get_cog("SafeMode")
    safemode_active = safemode_cog.safemode_active if safemode_cog else False
    
    total_members = sum(g.member_count for g in bot.guilds)
    total_channels = sum(len(g.channels) for g in bot.guilds)
    
    return {
        "guilds": len(bot.guilds),
        "members": total_members,
        "channels": total_channels,
        "safemode": safemode_active
    }

@router.post("/api/safemode/toggle")
async def toggle_safemode(request: Request):
    bot = check_admin(request)
    safemode_cog = bot.get_cog("SafeMode")
    
    if not safemode_cog:
        raise HTTPException(status_code=500, detail="SafeMode Cog not loaded")
        
    safemode_cog.safemode_active = not safemode_cog.safemode_active
    safemode_cog.save_config()
    
    return {"status": "success", "safemode": safemode_cog.safemode_active}

@router.get("/api/backups")
async def list_backups(request: Request):
    check_admin(request)
    BACKUPS_DIR = "backups"
    if not os.path.exists(BACKUPS_DIR):
        return {"backups": []}
        
    backups = sorted(os.listdir(BACKUPS_DIR), reverse=True)
    return {"backups": backups}

@router.get("/api/logs")
async def get_logs(request: Request):
    check_admin(request)
    # Read from data/cases.json
    try:
        with open("data/cases.json", "r", encoding="utf-8") as f:
            cases = json.load(f)
            # Return last 20 cases
            return {"logs": list(reversed(cases))[:20]}
    except:
        return {"logs": []}
