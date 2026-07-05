from fastapi import APIRouter, Request, HTTPException
import os
import json
import discord
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
    safemode_spam = safemode_cog.spam_protection if safemode_cog else True
    
    total_members = sum(g.member_count for g in bot.guilds)
    total_channels = sum(len(g.channels) for g in bot.guilds)
    
    return {
        "guilds": len(bot.guilds),
        "members": total_members,
        "channels": total_channels,
        "safemode": safemode_active,
        "safemode_spam": safemode_spam
    }

@router.post("/api/safemode/toggle")
async def toggle_safemode(request: Request, active: str = None, spam: str = "on"):
    bot = check_admin(request)
    safemode_cog = bot.get_cog("SafeMode")
    
    if not safemode_cog:
        raise HTTPException(status_code=500, detail="SafeMode Cog not loaded")
        
    if active is not None:
        safemode_cog.safemode_active = (active == "on")
    else:
        safemode_cog.safemode_active = not safemode_cog.safemode_active
        
    safemode_cog.spam_protection = (spam == "on")
    safemode_cog.save_config()
    
    return {
        "status": "success", 
        "safemode": safemode_cog.safemode_active,
        "safemode_spam": safemode_cog.spam_protection
    }



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
            # cases is a dict, we need to return a list of its values
            logs_list = list(cases.values())
            # Return last 20 cases
            return {"logs": list(reversed(logs_list))[:20]}
    except:
        return {"logs": []}

@router.get("/api/my_guilds")
async def get_my_guilds(request: Request):
    bot = check_admin(request)
    user_session = request.session.get("discord_user")
    uid = int(user_session["id"])
    
    guilds = []
    for g in bot.guilds:
        member = g.get_member(uid)
        if member and (g.owner_id == uid or member.guild_permissions.administrator):
            guilds.append({"id": str(g.id), "name": g.name})
    return {"guilds": guilds}


@router.get("/api/guilds/{guild_id}/channels")
async def get_channels(request: Request, guild_id: int):
    bot = check_admin(request)
    guild = bot.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
        
    channels = []
    for c in guild.text_channels:
        channels.append({"id": str(c.id), "name": c.name, "type": "text"})
    return {"channels": channels}

@router.get("/api/guilds/{guild_id}/members")
async def get_members(request: Request, guild_id: int):
    bot = check_admin(request)
    guild = bot.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
        
    members = []
    for m in guild.members[:100]:
        members.append({
            "id": str(m.id),
            "name": m.name,
            "display_name": m.display_name,
            "bot": m.bot
        })
    return {"members": members}

from pydantic import BaseModel

class SendMessageReq(BaseModel):
    channel_id: int
    content: str

@router.post("/api/chat/send")
async def send_chat(request: Request, req: SendMessageReq):
    bot = check_admin(request)
    channel = bot.get_channel(req.channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    try:
        await channel.send(req.content)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/members/{guild_id}/{member_id}/{action}")
async def member_action(request: Request, guild_id: int, member_id: int, action: str):
    bot = check_admin(request)
    guild = bot.get_guild(guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
        
    member = guild.get_member(member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    try:
        if action == "kick":
            await member.kick(reason="Kicked from Web Dashboard")
        elif action == "ban":
            await member.ban(reason="Banned from Web Dashboard")
        else:
            raise HTTPException(status_code=400, detail="Unknown action")
            
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/channels/{channel_id}/messages")
async def get_channel_messages(request: Request, channel_id: int):
    bot = check_admin(request)
    channel = bot.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    messages = []
    try:
        async for msg in channel.history(limit=50):
            messages.append({
                "id": str(msg.id),
                "author": str(msg.author),
                "author_avatar": msg.author.display_avatar.url if msg.author.display_avatar else None,
                "content": msg.content,
                "channel_name": str(channel.name),
                "created_at": msg.created_at.isoformat()
            })
        return {"messages": list(reversed(messages))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import UploadFile, File
from fastapi.responses import FileResponse
import shutil

@router.get("/api/backups/export/{filename}")
async def export_backup(request: Request, filename: str):
    check_admin(request)
    filepath = os.path.join("backups", filename)
    if not os.path.exists(filepath):
        filepath = os.path.join("data", filename)
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="File not found")
            
    if os.path.isdir(filepath):
        import tempfile
        # Create a temporary zip file
        zip_path = shutil.make_archive(os.path.join(tempfile.gettempdir(), filename), 'zip', filepath)
        return FileResponse(zip_path, filename=f"{filename}.zip")
        
    return FileResponse(filepath, filename=filename)

@router.post("/api/backups/import")
async def import_backup(request: Request, file: UploadFile = File(...)):
    check_admin(request)
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only JSON files are allowed")
        
    os.makedirs("data", exist_ok=True)
    filepath = os.path.join("data", file.filename)
    
    try:
        with open(filepath, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"status": "success", "message": f"Uploaded {file.filename} successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/server_logs")
async def get_server_logs(request: Request):
    check_admin(request)
    filepath = "data/server.log"
    if not os.path.exists(filepath):
        return {"logs": []}
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        # Parse lines to dict, taking last 100
        logs = []
        for line in reversed(lines[-100:]):
            line = line.strip()
            if not line: continue
            # Format: [2026-06-23 15:00:00 UTC] [JOIN] ...
            try:
                time_end = line.index("]")
                type_end = line.index("]", time_end + 1)
                
                time_str = line[1:time_end]
                type_str = line[time_end+3:type_end]
                content = line[type_end+2:]
                
                logs.append({
                    "time": time_str,
                    "type": type_str,
                    "content": content
                })
            except:
                logs.append({"time": "", "type": "RAW", "content": line})
                
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/server_logs/export")
async def export_server_logs(request: Request):
    check_admin(request)
    filepath = "data/server.log"
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Log file not found")
    return FileResponse(filepath, filename="server.log")

import httpx

@router.get("/api/user/lookup")
async def lookup_user(request: Request, q: str):
    """
    Lookup a user by UID or username.
    q = Discord user ID (digits) or display name to search in all guilds.
    """
    bot = check_admin(request)

    result = {
        "found_in_server": False,
        "discord_profile": None,
        "server_info": None,
        "warnings": [],
        "cases": []
    }

    # Determine if q is a UID or a name
    is_uid = q.strip().isdigit()
    target_id = int(q.strip()) if is_uid else None

    # --- Search in bot guilds ---
    found_member = None
    found_guild = None
    for guild in bot.guilds:
        if is_uid:
            m = guild.get_member(target_id)
        else:
            # Search by display name or username (case-insensitive)
            m = discord.utils.find(
                lambda mem: q.lower() in mem.name.lower() or q.lower() in mem.display_name.lower(),
                guild.members
            )
        if m:
            found_member = m
            found_guild = guild
            break

    if found_member:
        result["found_in_server"] = True
        result["server_info"] = {
            "guild_id": str(found_guild.id),
            "guild_name": found_guild.name,
            "display_name": found_member.display_name,
            "joined_at": found_member.joined_at.isoformat() if found_member.joined_at else None,
            "roles": [r.name for r in found_member.roles if r.name != "@everyone"],
            "is_banned": False
        }
        if not target_id:
            target_id = found_member.id

    # --- Fetch Discord public profile via API (works even if not in server) ---
    if target_id:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"https://discord.com/api/v10/users/{target_id}",
                    headers={"Authorization": f"Bot {bot.http.token}"}
                )
                if r.status_code == 200:
                    u = r.json()
                    avatar_hash = u.get("avatar")
                    avatar_url = (
                        f"https://cdn.discordapp.com/avatars/{target_id}/{avatar_hash}.png"
                        if avatar_hash else
                        f"https://cdn.discordapp.com/embed/avatars/{int(target_id) % 5}.png"
                    )
                    result["discord_profile"] = {
                        "id": str(target_id),
                        "username": u.get("username"),
                        "global_name": u.get("global_name"),
                        "avatar": avatar_url,
                        "bot": u.get("bot", False),
                        "created_at": str(discord.utils.snowflake_time(target_id).isoformat())
                    }
        except Exception:
            pass

    # --- Load local warnings & cases ---
    if target_id:
        try:
            with open("data/warnings.json", "r", encoding="utf-8") as f:
                warnings_db = json.load(f)
            result["warnings"] = warnings_db.get(str(target_id), [])
        except:
            pass

        try:
            with open("data/cases.json", "r", encoding="utf-8") as f:
                cases_db = json.load(f)
            result["cases"] = [
                c for c in cases_db.values()
                if str(c.get("target_id")) == str(target_id)
            ]
        except:
            pass

    if not result["discord_profile"] and not result["found_in_server"]:
        raise HTTPException(status_code=404, detail="User not found")

    return result

from pydantic import BaseModel as PydanticBase

class RunCommandReq(PydanticBase):
    channel_id: int
    command: str     # e.g. "warn", "ban"
    target: str      # user ID or name
    reason: str = ""
    bot_prefix: str = "!"  # "!" for bot or "?" for dyno

class MockContext:
    def __init__(self, bot, guild, author, channel):
        self.bot = bot
        self.guild = guild
        self.author = author
        self.channel = channel
        self.interaction = None
        self.sent_messages = []
        self.sent_embeds = []

    async def send(self, content=None, *, embed=None, embeds=None, view=None, ephemeral=False):
        if embed:
            self.sent_embeds.append(embed)
            try:
                await self.channel.send(embed=embed)
            except:
                pass
        if content:
            self.sent_messages.append(content)
            try:
                await self.channel.send(content)
            except:
                pass
        
        class MockMessage:
            def __init__(self):
                self.id = 123456789
        return MockMessage()

@router.post("/api/run_command")
async def run_command_api(request: Request, req: RunCommandReq):
    """
    Execute commands. If bot prefix is '!', execute via bot python code directly.
    If bot prefix is '?', send the message to the chat channel (for Dyno).
    """
    bot = check_admin(request)
    channel = bot.get_channel(req.channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
        
    guild = channel.guild
    target = req.target.strip()
    reason = req.reason.strip()

    # --- Case 1: Dyno commands (prefix "?") -> send via chat as before ---
    if req.bot_prefix == "?":
        if reason:
            msg = f"?{req.command} {target} {reason}"
        else:
            msg = f"?{req.command} {target}"
        try:
            await channel.send(msg)
            return {"status": "success", "sent": msg, "mode": "chat"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # --- Case 2: Our Bot commands (prefix "!") -> execute directly via Python Cog ---
    cog = bot.get_cog("Moderation")
    if not cog:
        raise HTTPException(status_code=500, detail="Moderation cog not found")

    user_session = request.session.get("discord_user")
    author_id = int(user_session["id"])
    author_member = guild.get_member(author_id)
    if not author_member:
        # Fallback to guild owner if administrator is executing from dashboard but not cached in member list
        author_member = guild.owner

    ctx = MockContext(bot, guild, author_member, channel)

    # 1. Resolve Target (Member, User ID, Case ID, or Amount)
    target_member = None
    target_id = None
    
    if req.command not in ["unban", "case", "purge"]:
        if target.isdigit():
            target_id = int(target)
            target_member = guild.get_member(target_id)
        else:
            # Search member by name
            target_member = discord.utils.find(
                lambda m: target.lower() in m.name.lower() or target.lower() in m.display_name.lower(),
                guild.members
            )
        if not target_member:
            raise HTTPException(status_code=400, detail=f"Không tìm thấy thành viên '{target}' trong server.")
    else:
        # Numeric parameters for unban, case, purge
        if target.isdigit():
            target_id = int(target)
        else:
            if req.command != "purge":
                raise HTTPException(status_code=400, detail="Đối tượng cho lệnh này phải là ID dạng số.")

    # 2. Execute corresponding command method in Cog
    try:
        if req.command == "warn":
            await cog.warn(ctx, target_member, reason=reason or "Không có lý do")
        elif req.command == "mute":
            duration = 60
            clean_reason = reason
            parts = reason.split(maxsplit=1)
            if parts and parts[0].isdigit():
                duration = int(parts[0])
                clean_reason = parts[1] if len(parts) > 1 else "Không có lý do"
            await cog.mute(ctx, target_member, duration, reason=clean_reason or "Không có lý do")
        elif req.command == "unmute":
            await cog.unmute(ctx, target_member)
        elif req.command == "kick":
            await cog.kick(ctx, target_member, reason=reason or "Không có lý do")
        elif req.command == "ban":
            await cog.ban(ctx, target_member, reason=reason or "Không có lý do")
        elif req.command == "unban":
            await cog.unban(ctx, target_id, reason=reason or "Kháng cáo được chấp nhận")
        elif req.command == "mutejail":
            await cog.mutejail(ctx, target_member, reason=reason or "Không có lý do")
        elif req.command == "unmutejail":
            await cog.unmutejail(ctx, target_member)
        elif req.command == "warns":
            await cog.warns(ctx, target_member)
        elif req.command == "clearwarns":
            await cog.clearwarns(ctx, target_member)
        elif req.command == "case":
            await cog.case(ctx, target_id)
        elif req.command == "purge":
            amount = 10
            if target.isdigit():
                amount = int(target)
            await cog.purge(ctx, amount)
        else:
            raise HTTPException(status_code=400, detail=f"Lệnh '{req.command}' chưa được hỗ trợ chạy trực tiếp.")

        # Collect response
        response_msg = ""
        if ctx.sent_messages:
            response_msg = "\n".join(ctx.sent_messages)
        elif ctx.sent_embeds:
            emb = ctx.sent_embeds[0]
            response_msg = f"Đã thực hiện: {emb.title or ''} {emb.description or ''}"
            
        return {
            "status": "success", 
            "sent": f"!{req.command} {target}", 
            "response": response_msg,
            "mode": "code"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi thực thi lệnh qua code: {str(e)}")



