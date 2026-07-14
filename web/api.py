from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import json
import discord
import random
import string
import io
import subprocess
import random
import time
import os
import base64
from config import cfg
from pydantic import BaseModel
router = APIRouter()
CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
@router.get("/api/captcha")
async def get_captcha(request: Request):
    code = "".join(random.choices(CHARS, k=5))
    request.session["captcha"] = code

    # Kích thước khung ảnh
    width, height = 240, 80  
    image = Image.new("RGB", (width, height), color="#f3f4f6")
    draw = ImageDraw.Draw(image)

    # 1. TẢI FONT CHỮ DÀY (BẮT BUỘC để chống bot)
    # Thử tải font Arial Bold hoặc Impact của hệ thống, nếu lỗi sẽ dùng font mặc định
    try:
        # Đường dẫn font phổ biến trên Linux (Ubuntu/Debian)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
    except IOError:
        try:
            # Nếu chạy trên Windows
            font = ImageFont.truetype("arialbd.ttf", 36)
        except IOError:
            font = ImageFont.load_default()

    # 2. VẼ TỪNG KÝ TỰ CÓ XOAY GÓC VÀ BIẾN DẠNG
    for i, char in enumerate(code):
        # Tạo một ảnh phụ tạm thời chỉ chứa 1 ký tự để xoay góc
        char_image = Image.new("RGBA", (50, 50), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_image)
        
        # Màu chữ ngẫu nhiên (tông màu tối)
        char_color = tuple(random.randint(10, 80) for _ in range(3))
        char_draw.text((10, 5), char, fill=char_color, font=font)
        
        # Xoay ký tự ngẫu nhiên từ -30 đến 30 độ (Bot cực kỳ ghét chữ bị xoay)
        angle = random.randint(-30, 30)
        rotated_char = char_image.rotate(angle, resample=Image.BICUBIC, expand=1)
        
        # Dán ký tự đã xoay vào ảnh chính (tính toán khoảng cách x để các chữ đè nhẹ lên nhau)
        x_pos = 15 + i * 38 + random.randint(-3, 3)
        y_pos = 15 + random.randint(-5, 5)
        image.paste(rotated_char, (x_pos, y_pos), rotated_char)

    # 3. TẠO NHIỄU ĐƯỜNG CONG ĐÈ LÊN CHỮ (Lines & Arcs)
    # Vẽ các đường thẳng cắt ngang chữ
    for _ in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        line_color = tuple(random.randint(80, 160) for _ in range(3))
        draw.line([(x1, y1), (x2, y2)], fill=line_color, width=random.randint(2, 3))

    # Vẽ thêm các đường vòng cung để cắt nát kết cấu chữ khi bot quét
    for _ in range(3):
        x1 = random.randint(0, width // 2)
        y1 = random.randint(0, height // 2)
        x2 = random.randint(width // 2, width)
        y2 = random.randint(height // 2, height)
        arc_color = tuple(random.randint(100, 180) for _ in range(3))
        draw.arc([x1, y1, x2, y2], start=random.randint(0, 90), end=random.randint(180, 360), fill=arc_color, width=2)

    # 4. TẠO NHIỄU HẠT (Salt & Pepper Noise) dày đặc
    for _ in range(150):
        x = random.randint(0, width)
        y = random.randint(0, height)
        dot_color = tuple(random.randint(0, 255) for _ in range(3))
        draw.point((x, y), fill=dot_color)

    # 5. LÀM MỜ NHẸ (Blur) ĐỂ BOT KHÔNG TÁCH ĐƯỢC CẠNH CHỮ
    # Việc làm mờ nhẹ khiến các thuật toán phân tách pixel của Bot bị sai lệch, nhưng mắt người vẫn đọc tốt
    image = image.filter(ImageFilter.SMOOTH_MORE)

    # Chuyển đổi sang Base64 trả về cho Web
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    base64_encoded = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

    return {
        "status": "success",
        "image": f"data:image/png;base64,{base64_encoded}"
    }


# ==========================================
# ENDPOINT: XÁC MINH CAPTCHA & GÁN ROLE
# ==========================================
class VerifyReq(BaseModel):
    captcha: str


@router.post("/api/verify_captcha")
async def verify(request: Request, req: VerifyReq):
    # --------------------------------------
    # Kiểm tra Đăng nhập & Discord Bot / Guild / Member giống hệt code cũ của bạn
    # --------------------------------------
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    bot = request.app.state.bot
    if not bot:
        raise HTTPException(status_code=500, detail="Bot chưa khởi động")

    guild = bot.get_guild(cfg.guild_id)
    if not guild:
        raise HTTPException(status_code=500, detail="Bot chưa tham gia server hoặc guild_id chưa được cấu hình")

    try:
        member = guild.get_member(int(uid))
        if member is None:
            member = await guild.fetch_member(int(uid))
    except discord.NotFound:
        raise HTTPException(status_code=400, detail="Bạn chưa tham gia server Discord.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # --------------------------------------
    # Logic Kiểm tra Captcha Bảo Mật (Đã sửa)
    # --------------------------------------
    real_code = request.session.get("captcha")

    if not real_code:
        raise HTTPException(status_code=400, detail="Captcha đã hết hạn hoặc không tồn tại.")

    # So sánh không phân biệt hoa thường
    if req.captcha.upper() != real_code.upper():
        raise HTTPException(status_code=400, detail="Sai Captcha.")

    # --------------------------------------
    # Kiểm tra & Gán Role Discord giống hệt code cũ của bạn
    # --------------------------------------
    if not cfg.verified_role_id:
        raise HTTPException(status_code=500, detail="Chưa cấu hình verified_role_id.")

    verified_role = guild.get_role(cfg.verified_role_id)
    if verified_role is None:
        raise HTTPException(status_code=500, detail=f"Không tìm thấy role ID {cfg.verified_role_id}.")

    # Đã xác minh trước đó
    if verified_role in member.roles:
        request.session.pop("captcha", None) # Xoá session ngay
        return {"status": "success", "message": "Bạn đã được xác minh rồi!"}

    try:
        await member.add_roles(verified_role, reason="Xác minh qua Web Captcha")
        if cfg.unverified_role_id:
            unverified_role = guild.get_role(cfg.unverified_role_id)
            if unverified_role is not None and unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="Đã xác minh qua Web Captcha")
    except discord.Forbidden:
        raise HTTPException(status_code=403, detail="Bot không có quyền gán role. Hãy đưa role Bot lên cao hơn role Verified.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # --------------------------------------
    # XÓA CAPTCHA SAU KHI THÀNH CÔNG (Tránh Replay Attack)
    # --------------------------------------
    request.session.pop("captcha", None)

    return {
        "status": "success",
        "message": f"Đã xác minh thành công! Đã gán role '{verified_role.name}'."
    }


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
    uid = int(request.session.get("uid"))
    
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

    uid = request.session.get("uid")
    author_id = int(uid)
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

from pydantic import BaseModel

class BulkLookupReq(BaseModel):
    queries: list[str]

async def perform_user_lookup(bot, q: str):
    is_uid = q.strip().isdigit()
    target_id = int(q.strip()) if is_uid else None

    result = {
        "query": q,
        "found": False,
        "discord_profile": None,
        "joined_servers": [],
        "warnings": [],
        "cases": []
    }

    # Find mutual guilds + presence info
    mutual_guilds = []
    found_member_global = None
    presence_info = None

    for guild in bot.guilds:
        member = None
        if is_uid:
            member = guild.get_member(target_id)
        else:
            member = discord.utils.find(
                lambda m: q.lower() in m.name.lower() or q.lower() in m.display_name.lower(),
                guild.members
            )
        if member:
            found_member_global = member
            if not target_id:
                target_id = member.id

            # --- Presence / Activity ---
            if presence_info is None and member.status != discord.Status.offline:
                activities = []
                for act in member.activities:
                    if isinstance(act, discord.Spotify):
                        activities.append({
                            "type": "Spotify",
                            "title": act.title,
                            "artist": act.artist,
                            "album": act.album,
                        })
                    elif isinstance(act, discord.Game):
                        activities.append({"type": "Game", "name": act.name})
                    elif isinstance(act, discord.Streaming):
                        activities.append({"type": "Streaming", "name": act.name, "url": act.url})
                    elif isinstance(act, discord.CustomActivity):
                        activities.append({"type": "Custom", "state": str(act.name or act.state or "")})
                    elif act:
                        activities.append({"type": "Activity", "name": str(act.name or "")})

                presence_info = {
                    "status": str(member.status),
                    "mobile": member.is_on_mobile(),
                    "activities": activities
                }

            mutual_guilds.append({
                "guild_id": str(guild.id),
                "guild_name": guild.name,
                "display_name": member.display_name,
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "roles": [r.name for r in member.roles if r.name != "@everyone"],
                "is_admin": member.guild_permissions.administrator if member.guild_permissions else False,
            })

    result["joined_servers"] = mutual_guilds
    result["presence"] = presence_info

    # Kiểm tra nếu người dùng đích đã từng đăng nhập (lưu trong data/users.json)
    stored_user = None
    try:
        if os.path.exists("data/users.json"):
            with open("data/users.json", "r", encoding="utf-8") as f:
                users_db = json.load(f)
                if target_id:
                    stored_user = users_db.get(str(target_id))
                else:
                    # Tìm kiếm bằng username hoặc global_name nếu chỉ nhập chữ
                    for u_data in users_db.values():
                        u_name = u_data.get("username", "").lower()
                        g_name = u_data.get("global_name", "")
                        g_name = g_name.lower() if g_name else ""
                        if q.lower() == u_name or q.lower() == g_name:
                            stored_user = u_data
                            target_id = int(u_data["id"])
                            break

                if stored_user and "guilds" in stored_user:
                    for sg in stored_user["guilds"]:
                        # Tránh trùng lặp với các server chung bot đã quét
                        existing = any(str(g["guild_id"]) == str(sg["id"]) for g in mutual_guilds)
                        if not existing:
                            mutual_guilds.append({
                                "guild_id": str(sg["id"]),
                                "guild_name": sg["name"],
                                "display_name": stored_user.get("global_name") or stored_user.get("username", "Thành viên"),
                                "joined_at": None,
                                "roles": [],
                                "is_admin": (int(sg.get("permissions", 0)) & 0x8) != 0, # Quyền Admin (0x8)
                                "via_oauth2": True # Đánh dấu lấy từ lịch sử đăng nhập OAuth2
                            })
    except Exception as e:
        print(f"Lỗi đọc data/users.json trong lookup: {e}")



    # Fetch public Discord profile if UID is resolved
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
                    result["found"] = True
        except Exception:
            pass

        # Load warnings & cases
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

    if found_member_global and not result["discord_profile"]:
        avatar_url = found_member_global.display_avatar.url if found_member_global.display_avatar else f"https://cdn.discordapp.com/embed/avatars/{int(target_id) % 5}.png"
        result["discord_profile"] = {
            "id": str(target_id),
            "username": found_member_global.name,
            "global_name": found_member_global.display_name,
            "avatar": avatar_url,
            "bot": found_member_global.bot,
            "created_at": str(discord.utils.snowflake_time(target_id).isoformat())
        }
        result["found"] = True

    return result

@router.get("/api/public/lookup")
async def public_lookup(request: Request, q: str):
    bot = request.app.state.bot
    if not bot:
        raise HTTPException(status_code=500, detail="Bot is not running")
    res = await perform_user_lookup(bot, q)
    if not res["found"] and not res["joined_servers"]:
        raise HTTPException(status_code=404, detail="User not found")
    return res

@router.post("/api/public/bulk_lookup")
async def public_bulk_lookup(request: Request, req: BulkLookupReq):
    bot = request.app.state.bot
    if not bot:
        raise HTTPException(status_code=500, detail="Bot is not running")
    results = []
    for query in req.queries:
        query_stripped = query.strip()
        if not query_stripped:
            continue
        try:
            res = await perform_user_lookup(bot, query_stripped)
            results.append(res)
        except Exception as e:
            results.append({
                "query": query_stripped,
                "found": False,
                "error": str(e)
            })
    return {"results": results}


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY API – Captcha xác minh nhận role "Dân thường"
# ─────────────────────────────────────────────────────────────────────────────

# class VerifyReq(BaseModel):
#     captcha: str

# @router.post("/api/verify")
# async def verify_user(request: Request, req: VerifyReq):
#     uid = request.session.get("uid")
#     if not uid:
#         raise HTTPException(status_code=401, detail="Chưa đăng nhập")

#     bot = request.app.state.bot
#     if not bot:
#         raise HTTPException(status_code=500, detail="Bot chưa khởi động")

#     guild = bot.get_guild(cfg.guild_id)
#     if not guild:
#         raise HTTPException(status_code=400, detail="Bot chưa tham gia server hoặc guild_id chưa được cấu hình")

#     try:
#         member = guild.get_member(int(uid))
#         if not member:
#             member = await guild.fetch_member(int(uid))
#     except discord.NotFound:
#         raise HTTPException(status_code=400, detail="Bạn chưa tham gia server Discord. Hãy tham gia trước khi xác minh!")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

#     if not cfg.verified_role_id:
#         raise HTTPException(status_code=400, detail="Role xác minh chưa được cấu hình (verified_role_id = 0)")

#     role = guild.get_role(cfg.verified_role_id)
#     if not role:
#         raise HTTPException(status_code=400, detail=f"Không tìm thấy role ID {cfg.verified_role_id} trong server")

#     # Kiểm tra xem đã có role chưa
#     if role in member.roles:
#         return {"status": "success", "message": "Bạn đã được xác minh rồi!"}

#     try:
#         # Gán role Verified
#         await member.add_roles(role, reason="Xác minh qua Web Captcha")

#         # Xóa role Unverified nếu có cấu hình và thành viên đang có role đó
#         if cfg.unverified_role_id:
#             unverified_role = guild.get_role(cfg.unverified_role_id)
#             if unverified_role and unverified_role in member.roles:
#                 try:
#                     await member.remove_roles(unverified_role, reason="Đã xác minh qua Web Captcha")
#                 except Exception as re:
#                     print(f"[verify_api] Không thể gỡ role unverified cho {member.id}: {re}")

#         return {"status": "success", "message": f"Đã xác minh và gán role '{role.name}' thành công!"}
#     except discord.Forbidden:
#         raise HTTPException(status_code=403, detail="Bot không có quyền gán role này. Hãy đặt role Bot cao hơn role cần gán.")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
def check_admin(request: Request):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")

    bot = request.app.state.bot
    if not bot:
        raise HTTPException(status_code=500, detail="Bot is not running")

    uid_int = int(uid)

    # Kiểm tra: user có phải admin trong bất kỳ guild nào bot quản lý không
    is_admin = False
    for guild in bot.guilds:
        member = guild.get_member(uid_int)
        if member and (guild.owner_id == uid_int or member.guild_permissions.administrator):
            is_admin = True
            break

    if not is_admin:
        raise HTTPException(status_code=403, detail="Forbidden: You are not an administrator")

    return bot

def get_current_user(request: Request):
    """Lấy thông tin user từ server-side store dựa theo uid trong session cookie."""
    uid = request.session.get("uid")
    if not uid:
        return None
    return request.app.state.user_store.get(uid)



# ─────────────────────────────────────────────────────────────────────────────
# APPEALS API – Hệ thống kháng cáo đồng bộ Web & Discord
# ─────────────────────────────────────────────────────────────────────────────

import uuid
from datetime import datetime

APPEALS_FILE = "data/appeals.json"

def load_appeals() -> dict:
    try:
        if os.path.exists(APPEALS_FILE):
            with open(APPEALS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {}

def save_appeals(db: dict):
    os.makedirs("data", exist_ok=True)
    with open(APPEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

class AppealSubmitReq(BaseModel):
    violation: str
    explanation: str
    case_id: str = ""

class SendMessageReq(BaseModel):
    content: str

class UpdateStatusReq(BaseModel):
    status: str


@router.post("/api/public/appeal")
async def submit_appeal(request: Request, req: AppealSubmitReq):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    user_data = request.app.state.user_store.get(uid, {})
    username = user_data.get("username", "Unknown")
    avatar_url = user_data.get("avatar_url", "")

    db = load_appeals()

    # Kiểm tra xem đã có đơn đang pending chưa
    for appeal in db.values():
        if appeal["user_id"] == uid and appeal["status"] == "pending":
            raise HTTPException(status_code=400, detail="Bạn đã có đơn kháng cáo đang chờ xử lý. Vui lòng đợi phản hồi!")

    appeal_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()

    new_appeal = {
        "id": appeal_id,
        "user_id": uid,
        "username": username,
        "avatar_url": avatar_url,
        "violation": req.violation,
        "explanation": req.explanation,
        "case_id": req.case_id,
        "status": "pending",
        "thread_id": None,
        "created_at": now,
        "messages": [
            {
                "sender": "appellant",
                "sender_name": username,
                "content": f"📋 **Đơn kháng cáo mới**\n\n**Vi phạm bị xử phạt:** {req.violation}\n\n**Giải trình:** {req.explanation}\n\n**Case ID:** {req.case_id or 'Không cung cấp'}",
                "timestamp": now
            }
        ]
    }

    db[appeal_id] = new_appeal
    save_appeals(db)

    # Gửi lên kênh Staff trên Discord và tạo Thread
    bot = request.app.state.bot
    if bot and cfg.appeal_channel_id:
        try:
            channel = bot.get_channel(cfg.appeal_channel_id)
            if channel:
                import discord as disc
                embed = disc.Embed(
                    title="📨 Kháng Cáo Mới từ Web",
                    color=0x5865F2,
                    description=f"Người dùng **{username}** (`{uid}`) gửi đơn kháng cáo qua trang web."
                )
                embed.add_field(name="Vi phạm bị xử phạt", value=req.violation, inline=False)
                embed.add_field(name="Giải trình", value=req.explanation, inline=False)
                embed.add_field(name="Case ID", value=req.case_id or "Không cung cấp", inline=True)
                embed.add_field(name="Appeal ID", value=f"`{appeal_id}`", inline=True)
                embed.set_thumbnail(url=avatar_url)
                embed.set_footer(text="Trả lời trong Thread để đồng bộ về Web · Web Appeal System")

                msg = await channel.send(embed=embed)
                # Tạo Thread gắn với tin nhắn này
                thread = await msg.create_thread(
                    name=f"Kháng cáo - {username} [{appeal_id}]",
                    auto_archive_duration=10080  # 7 ngày
                )

                # Lưu thread_id vào database
                db[appeal_id]["thread_id"] = str(thread.id)
                save_appeals(db)
        except Exception as e:
            print(f"Lỗi gửi Discord appeal: {e}")

    return {"status": "success", "appeal_id": appeal_id}


@router.get("/api/appeals")
async def get_appeals(request: Request):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    db = load_appeals()

    # Kiểm tra quyền admin
    user_data = request.app.state.user_store.get(uid, {})
    is_admin_user = any(
        g.get("owner") or (int(g.get("permissions", 0)) & 0x20)
        for g in user_data.get("guilds", [])
    )

    if is_admin_user:
        appeals = sorted(db.values(), key=lambda a: a.get("created_at", ""), reverse=True)
    else:
        appeals = [a for a in db.values() if a["user_id"] == uid]
        appeals.sort(key=lambda a: a.get("created_at", ""), reverse=True)

    return {"appeals": appeals}


@router.get("/api/appeals/{appeal_id}/messages")
async def get_appeal_messages(request: Request, appeal_id: str):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    db = load_appeals()
    appeal = db.get(appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn kháng cáo")

    # Người dùng thường chỉ được đọc kháng cáo của chính họ
    user_data = request.app.state.user_store.get(uid, {})
    is_admin_user = any(
        g.get("owner") or (int(g.get("permissions", 0)) & 0x20)
        for g in user_data.get("guilds", [])
    )
    if not is_admin_user and appeal["user_id"] != uid:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập")

    return {
        "status": appeal["status"],
        "messages": appeal.get("messages", []),
        "id": appeal_id,
        "username": appeal.get("username")
    }


@router.post("/api/appeals/{appeal_id}/messages")
async def send_appeal_message(request: Request, appeal_id: str, req: SendMessageReq):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    db = load_appeals()
    appeal = db.get(appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn kháng cáo")

    user_data = request.app.state.user_store.get(uid, {})
    username = user_data.get("username", "Unknown")
    is_admin_user = any(
        g.get("owner") or (int(g.get("permissions", 0)) & 0x20)
        for g in user_data.get("guilds", [])
    )

    # Kiểm tra quyền
    if not is_admin_user and appeal["user_id"] != uid:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập")

    sender_role = "staff" if is_admin_user else "appellant"
    now = datetime.utcnow().isoformat()

    msg_entry = {
        "sender": sender_role,
        "sender_name": username,
        "content": req.content,
        "timestamp": now
    }

    db[appeal_id]["messages"].append(msg_entry)
    save_appeals(db)

    # Đồng bộ tin nhắn lên Discord Thread
    bot = request.app.state.bot
    thread_id = appeal.get("thread_id")
    if bot and thread_id:
        try:
            thread = bot.get_channel(int(thread_id))
            if thread:
                prefix = "👤 [Người dùng]" if sender_role == "appellant" else "🛡️ [Staff]"
                await thread.send(f"{prefix} **{username}**: {req.content}")
        except Exception as e:
            print(f"Lỗi đồng bộ tin nhắn lên Discord: {e}")

    return {
        "status": db[appeal_id]["status"],
        "messages": db[appeal_id]["messages"]
    }


@router.post("/api/appeals/{appeal_id}/status")
async def update_appeal_status(request: Request, appeal_id: str, req: UpdateStatusReq):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    user_data = request.app.state.user_store.get(uid, {})
    is_admin_user = any(
        g.get("owner") or (int(g.get("permissions", 0)) & 0x20)
        for g in user_data.get("guilds", [])
    )
    if not is_admin_user:
        raise HTTPException(status_code=403, detail="Chỉ Admin mới có thể cập nhật trạng thái")

    if req.status not in ["pending", "accepted", "rejected"]:
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ")

    db = load_appeals()
    appeal = db.get(appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn kháng cáo")

    old_status = appeal["status"]
    db[appeal_id]["status"] = req.status
    username = appeal.get("username", "Unknown")
    admin_name = user_data.get("username", "Admin")
    now = datetime.utcnow().isoformat()

    status_msg = {
        "accepted": f"✅ Kháng cáo của bạn đã được **chấp nhận** bởi {admin_name}. Chúc mừng bạn trở lại!",
        "rejected": f"❌ Kháng cáo của bạn bị **từ chối** bởi {admin_name}. Nếu cần hỗ trợ thêm, hãy liên hệ Admin.",
        "pending": f"🔄 Đơn kháng cáo được chuyển lại trạng thái chờ duyệt bởi {admin_name}."
    }

    db[appeal_id]["messages"].append({
        "sender": "staff",
        "sender_name": "Hệ thống",
        "content": status_msg.get(req.status, f"Trạng thái đã cập nhật thành {req.status}"),
        "timestamp": now
    })
    save_appeals(db)

    # Đồng bộ thông báo lên Discord Thread và DM người dùng
    bot = request.app.state.bot
    thread_id = appeal.get("thread_id")
    if bot:
        try:
            # Gửi vào Thread
            if thread_id:
                thread = bot.get_channel(int(thread_id))
                if thread:
                    color = 0x22c55e if req.status == "accepted" else (0xef4444 if req.status == "rejected" else 0x5865F2)
                    import discord as disc
                    embed = disc.Embed(
                        title=f"{'✅' if req.status == 'accepted' else '❌'} Kháng cáo {req.status.upper()}",
                        description=status_msg.get(req.status),
                        color=color
                    )
                    await thread.send(embed=embed)

            # DM người dùng nếu có thể
            appellant_uid = appeal.get("user_id")
            if appellant_uid:
                user_obj = await bot.fetch_user(int(appellant_uid))
                if user_obj:
                    import discord as disc
                    embed = disc.Embed(
                        title=f"{'✅' if req.status == 'accepted' else '❌'} Cập nhật kháng cáo",
                        description=status_msg.get(req.status),
                        color=0x22c55e if req.status == "accepted" else 0xef4444
                    )
                    embed.set_footer(text="Xem chi tiết tại: bot.thuychi.cloud/appeals")
                    try:
                        await user_obj.send(embed=embed)
                    except:
                        pass
        except Exception as e:
            print(f"Lỗi đồng bộ trạng thái lên Discord: {e}")

    return {"status": req.status, "message": f"Đã cập nhật trạng thái thành {req.status}"}
# =====================================================================
# BỔ SUNG 1: ĐÓNG ĐƠN KHÁNG CÁO (DÀNH CHO ADMIN BÊN WEB)
# =====================================================================
@router.post("/api/appeals/{appeal_id}/close")
async def close_appeal(request: Request, appeal_id: str):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    user_data = request.app.state.user_store.get(uid, {})
    is_admin_user = any(
        g.get("owner") or (int(g.get("permissions", 0)) & 0x20)
        for g in user_data.get("guilds", [])
    )
    if not is_admin_user:
        raise HTTPException(status_code=403, detail="Chỉ Admin mới có thể đóng đơn")

    db = load_appeals()
    appeal = db.get(appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn kháng cáo")

    admin_name = user_data.get("username", "Admin")
    now = datetime.utcnow().isoformat()

    # Cập nhật trạng thái thành closed
    db[appeal_id]["status"] = "closed"
    db[appeal_id]["messages"].append({
        "sender": "staff",
        "sender_name": "Hệ thống",
        "content": f"🔒 Đơn kháng cáo đã được **Đóng lại** bởi {admin_name}. Phiên hỗ trợ kết thúc.",
        "timestamp": now
    })
    save_appeals(db)

    # Đồng bộ đóng và khóa Thread trên Discord
    bot = request.app.state.bot
    thread_id = appeal.get("thread_id")
    if bot and thread_id:
        try:
            thread = bot.get_channel(int(thread_id))
            if thread:
                import discord as disc
                embed = disc.Embed(
                    title="🔒 Đơn Kháng Cáo Đã Đóng",
                    description=f"Đơn kháng cáo đã được đóng bởi Admin **{admin_name}** từ trang Web.",
                    color=0x6b7280
                )
                await thread.send(embed=embed)
                # Khóa và lưu trữ thread
                await thread.edit(locked=True, archived=True)
        except Exception as e:
            print(f"Lỗi khóa thread Discord khi đóng đơn: {e}")

    return {"status": "closed", "message": "Đã đóng đơn kháng cáo và khóa thread thành công."}


# =====================================================================
# BỔ SUNG 2: THU HỒI ĐƠN KHÁNG CÁO (DÀNH CHO NGƯỜI DÙNG)
# =====================================================================
@router.post("/api/public/appeal/{appeal_id}/revoke")
async def revoke_appeal(request: Request, appeal_id: str):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    db = load_appeals()
    appeal = db.get(appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn kháng cáo")

    # Kiểm tra xem có đúng chủ sở hữu đơn không
    if appeal["user_id"] != uid:
        raise HTTPException(status_code=403, detail="Bạn không có quyền thu hồi đơn này")

    # Chỉ cho phép thu hồi khi đơn đang ở trạng thái pending
    if appeal["status"] != "pending":
        raise HTTPException(status_code=400, detail="Chỉ có thể thu hồi đơn đang chờ xử lý")

    # Thực hiện xóa đơn khỏi file JSON (Thu hồi hoàn toàn)
    thread_id = appeal.get("thread_id")
    del db[appeal_id]
    save_appeals(db)

    # Thông báo và khóa Thread Discord bên phía Staff
    bot = request.app.state.bot
    if bot and thread_id:
        try:
            thread = bot.get_channel(int(thread_id))
            if thread:
                await thread.send("🗑️ *Đơn kháng cáo này đã được người dùng chủ động thu hồi từ trang Web.*")
                await thread.edit(locked=True, archived=True)
        except Exception as e:
            print(f"Lỗi xử lý thread Discord khi thu hồi đơn: {e}")

    return {"status": "success", "message": "Thu hồi đơn kháng cáo thành công!"}


# =====================================================================
# BỔ SUNG 3: TRA CỨU ĐƠN KHÁNG CÁO NHANH (DÀNH CHO NGƯỜI DÙNG)
# =====================================================================
@router.get("/api/public/appeal/track")
async def track_appeal(request: Request):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập")

    db = load_appeals()
    
    # Lấy ra tất cả đơn của user này và xếp đơn mới nhất lên đầu
    user_appeals = [a for a in db.values() if a["user_id"] == uid]
    if not user_appeals:
        return {"has_appeal": False, "message": "Bạn chưa từng gửi đơn kháng cáo nào."}

    user_appeals.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    latest_appeal = user_appeals[0]

    return {
        "has_appeal": True,
        "latest_appeal": {
            "id": latest_appeal["id"],
            "status": latest_appeal["status"],
            "violation": latest_appeal["violation"],
            "created_at": latest_appeal["created_at"],
            "case_id": latest_appeal.get("case_id", "")
        }
    }