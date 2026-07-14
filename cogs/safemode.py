import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
from datetime import datetime, timezone, timedelta
import asyncio

from config import cfg

# Setup timezone cho VN (GMT+7)
VN_TZ = timezone(timedelta(hours=7))

DATA_DIR = "data"
BACKUPS_DIR = "backups"
CONFIG_FILE = os.path.join(DATA_DIR, "safemode_config.json")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUPS_DIR, exist_ok=True)

class SafeMode(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.safemode_active = False
        self.spam_protection = True
        self.whitelist = set()
        self.schedule_start = None
        self.schedule_end = None
        self.action_tracker = {}
        
        self.load_config()
        self.schedule_task.start()

    def cog_unload(self):
        self.schedule_task.cancel()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.safemode_active = data.get("active", False)
                    self.spam_protection = data.get("spam_protection", True)
                    self.whitelist = set(data.get("whitelist", []))
                    self.schedule_start = data.get("schedule_start", None)
                    self.schedule_end = data.get("schedule_end", None)
            except Exception as e:
                print(f"Lỗi load safemode_config: {e}")
    
    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "active": self.safemode_active,
                "spam_protection": self.spam_protection,
                "whitelist": list(self.whitelist),
                "schedule_start": self.schedule_start,
                "schedule_end": self.schedule_end
            }, f, indent=4)


    async def check_permissions(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == interaction.guild.owner_id or interaction.user.guild_permissions.administrator:
            return True
        msg = "❌ Bạn không có quyền sử dụng lệnh này (Yêu cầu: Admin/Owner)."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(msg, ephemeral=True)
            except Exception:
                pass
        return False

    @app_commands.command(name="safemode", description="Bật/Tắt chế độ bảo vệ khẩn cấp")
    @app_commands.choices(state=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off")
    ])
    @app_commands.choices(spam=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off")
    ])
    async def safemode_cmd(self, interaction: discord.Interaction, state: str, spam: str = "on"):
        try:
            await interaction.response.defer()
        except Exception:
            pass

        if not await self.check_permissions(interaction):
            return

        if state == "on":
            self.safemode_active = True
            self.spam_protection = (spam == "on")
            self.save_config()
            
            # Thực hiện backup
            backup_path = await self._create_backup(interaction.guild)
            
            embed = discord.Embed(title="🛡 SafeMode Enabled", color=0x00FF00)
            embed.add_field(name="Protection", value="Active", inline=True)
            embed.add_field(name="Spam Filter", value="ON" if self.spam_protection else "OFF", inline=True)
            if backup_path:
                embed.add_field(name="Backup Created", value=f"Saved to `{backup_path}`", inline=False)
            
            await interaction.followup.send(embed=embed)
        else:
            self.safemode_active = False
            self.save_config()
            await interaction.followup.send("✅ SafeMode Disabled", ephemeral=False)


    @app_commands.command(name="backup", description="Tạo snapshot thủ công cho server")
    async def backup_cmd(self, interaction: discord.Interaction):
        # Defer ngay lập tức trước mọi tác vụ
        try:
            await interaction.response.defer()
        except Exception:
            pass

        if not await self.check_permissions(interaction):
            return
        
        backup_path = await self._create_backup(interaction.guild)
        
        if backup_path:
            await interaction.followup.send(f"✅ Đã tạo backup tại: `{backup_path}`")
        else:
            await interaction.followup.send("❌ Lỗi khi tạo backup.")

    async def _create_backup(self, guild: discord.Guild) -> str:
        timestamp = datetime.now(VN_TZ).strftime("%Y-%m-%d_%H-%M")
        backup_path = os.path.join(BACKUPS_DIR, timestamp)
        os.makedirs(backup_path, exist_ok=True)
        
        try:
            # 1. Backup roles
            roles_data = []
            for role in guild.roles:
                roles_data.append({
                    "id": role.id,
                    "name": role.name,
                    "permissions": role.permissions.value,
                    "color": role.color.value,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable,
                    "position": role.position
                })
            with open(os.path.join(backup_path, "roles.json"), "w", encoding="utf-8") as f:
                json.dump(roles_data, f, indent=4)
                
            # 2. Backup channels
            channels_data = []
            for channel in guild.channels:
                c_data = {
                    "id": channel.id,
                    "name": channel.name,
                    "type": str(channel.type),
                    "position": channel.position,
                    "category_id": channel.category_id,
                }
                channels_data.append(c_data)
            with open(os.path.join(backup_path, "channels.json"), "w", encoding="utf-8") as f:
                json.dump(channels_data, f, indent=4)
                
            # 3. Backup members
            members_data = []
            for member in guild.members:
                if not member.bot:
                    members_data.append({
                        "id": member.id,
                        "roles": [r.id for r in member.roles if r.id != guild.default_role.id]
                    })
            with open(os.path.join(backup_path, "members.json"), "w", encoding="utf-8") as f:
                json.dump(members_data, f, indent=4)
                
            # 4. Backup audit log (last 100 entries)
            audit_data = []
            if guild.me.guild_permissions.view_audit_log:
                async for entry in guild.audit_logs(limit=100):
                    audit_data.append({
                        "user": str(entry.user),
                        "user_id": entry.user.id if entry.user else None,
                        "action": str(entry.action),
                        "target": str(entry.target),
                        "time": entry.created_at.isoformat()
                    })
            with open(os.path.join(backup_path, "audit.json"), "w", encoding="utf-8") as f:
                json.dump(audit_data, f, indent=4)
                
            return backup_path
        except Exception as e:
            print(f"Backup Error: {e}")
            return None

    @app_commands.command(name="restore", description="Khôi phục snapshot (Hỗ trợ qua server mới)")
    @app_commands.choices(type=[
        app_commands.Choice(name="Latest", value="latest"),
        app_commands.Choice(name="Roles", value="roles"),
        app_commands.Choice(name="Channels", value="channels"),
        app_commands.Choice(name="Members", value="members")
    ])
    async def restore_cmd(self, interaction: discord.Interaction, type: str):
        try:
            await interaction.response.defer()
        except Exception:
            pass

        if not await self.check_permissions(interaction):
            return
        
        if not os.path.exists(BACKUPS_DIR):
            await interaction.followup.send("❌ Không có backup nào.")
            return
            
        backups = sorted(os.listdir(BACKUPS_DIR), reverse=True)
        if not backups:
            await interaction.followup.send("❌ Không có backup nào.")
            return
            
        latest_backup = os.path.join(BACKUPS_DIR, backups[0])
        guild = interaction.guild
        
        log_msgs = [f"Bắt đầu khôi phục từ bản sao lưu: `{backups[0]}` (Hỗ trợ server mới)..."]
        await interaction.followup.send("\n".join(log_msgs))

        try:
            role_map = {} # old_id: new_role
            category_map = {} # old_id: new_category
            
            # 1. RESTORE ROLES (Và map ID cũ sang ID mới)
            if type in ["latest", "roles", "members"]:
                roles_file = os.path.join(latest_backup, "roles.json")
                if os.path.exists(roles_file):
                    with open(roles_file, "r", encoding="utf-8") as f:
                        roles_data = json.load(f)
                    existing_roles = {r.name: r for r in guild.roles}
                    created = 0
                    for r_data in roles_data:
                        old_id = r_data["id"]
                        role_name = r_data["name"]
                        if role_name == "@everyone":
                            role_map[old_id] = guild.default_role
                            continue
                            
                        if role_name in existing_roles:
                            role_map[old_id] = existing_roles[role_name]
                        else:
                            if type in ["latest", "roles"]: # Chỉ tạo nếu user yêu cầu
                                new_role = await guild.create_role(
                                    name=role_name,
                                    permissions=discord.Permissions(r_data["permissions"]),
                                    color=discord.Color(r_data["color"]),
                                    hoist=r_data["hoist"],
                                    mentionable=r_data["mentionable"],
                                    reason="SafeMode Restore"
                                )
                                role_map[old_id] = new_role
                                created += 1
                                await asyncio.sleep(0.5)
                    if type in ["latest", "roles"]:
                        log_msgs.append(f"✅ Đã khôi phục {created} roles.")
                
            # 2. RESTORE CHANNELS & CATEGORIES
            if type in ["latest", "channels"]:
                channels_file = os.path.join(latest_backup, "channels.json")
                if os.path.exists(channels_file):
                    with open(channels_file, "r", encoding="utf-8") as f:
                        channels_data = json.load(f)
                    
                    existing_channels = {c.name: c for c in guild.channels}
                    
                    # Tạo categories trước
                    created_cat = 0
                    for c_data in channels_data:
                        if c_data["type"] == "category":
                            old_id = c_data["id"]
                            cat_name = c_data["name"]
                            if cat_name in existing_channels:
                                category_map[old_id] = existing_channels[cat_name]
                            else:
                                new_cat = await guild.create_category(name=cat_name, reason="SafeMode Restore")
                                category_map[old_id] = new_cat
                                created_cat += 1
                                await asyncio.sleep(0.5)
                                
                    # Tạo channels
                    created_ch = 0
                    for c_data in channels_data:
                        if c_data["type"] != "category":
                            ch_name = c_data["name"]
                            if ch_name not in existing_channels:
                                new_cat = category_map.get(c_data.get("category_id"))
                                if "text" in c_data["type"]:
                                    await guild.create_text_channel(name=ch_name, category=new_cat, reason="SafeMode Restore")
                                elif "voice" in c_data["type"]:
                                    await guild.create_voice_channel(name=ch_name, category=new_cat, reason="SafeMode Restore")
                                created_ch += 1
                                await asyncio.sleep(0.5)
                                
                    log_msgs.append(f"✅ Đã khôi phục {created_cat} categories và {created_ch} channels.")
                    
            # 3. RESTORE MEMBERS (Phải dùng role_map vì ID ở server mới bị thay đổi)
            if type in ["latest", "members"]:
                members_file = os.path.join(latest_backup, "members.json")
                if os.path.exists(members_file):
                    with open(members_file, "r", encoding="utf-8") as f:
                        members_data = json.load(f)
                    restored = 0
                    for m_data in members_data:
                        member = guild.get_member(m_data["id"])
                        if member:
                            roles_to_add = []
                            for old_r_id in m_data["roles"]:
                                new_role = role_map.get(old_r_id)
                                if new_role and new_role not in member.roles and new_role != guild.default_role:
                                    roles_to_add.append(new_role)
                            if roles_to_add:
                                try:
                                    await member.add_roles(*roles_to_add, reason="SafeMode Restore")
                                    restored += 1
                                    await asyncio.sleep(0.5)
                                except discord.Forbidden:
                                    pass
                    log_msgs.append(f"✅ Đã khôi phục roles cho {restored} members.")
                    
            log_msgs.append("🎉 **Hoàn tất khôi phục!**")
            await interaction.channel.send("\n".join(log_msgs))
            
        except Exception as e:
            await interaction.channel.send(f"❌ Lỗi trong quá trình khôi phục: {e}")
        
    @app_commands.command(name="reportserver", description="Xuất báo cáo server")
    async def reportserver_cmd(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title="📊 Server Report", color=discord.Color.blue())
        
        members = guild.member_count
        bots = sum(1 for m in guild.members if m.bot)
        roles = len(guild.roles)
        channels = len(guild.channels)
        categories = len(guild.categories)
        try:
            webhooks = len(await guild.webhooks())
        except discord.Forbidden:
            webhooks = "No permission"
            
        boost_level = guild.premium_tier
        
        embed.add_field(name="👥 Members", value=f"Total: {members}\nBots: {bots}", inline=True)
        embed.add_field(name="🛡️ Roles", value=str(roles), inline=True)
        embed.add_field(name="📺 Channels", value=f"Channels: {channels}\nCategories: {categories}", inline=True)
        embed.add_field(name="🔗 Webhooks", value=str(webhooks), inline=True)
        embed.add_field(name="🚀 Boost Level", value=f"Level {boost_level}", inline=True)
        embed.add_field(name="🛡 SafeMode Status", value="ON" if self.safemode_active else "OFF", inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="lockdown", description="Khóa server khẩn cấp")
    async def lockdown_cmd(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except Exception:
            pass

        if not await self.check_permissions(interaction):
            return
        guild = interaction.guild
        default_role = guild.default_role
        
        perms = default_role.permissions
        perms.update(
            send_messages=False,
            create_public_threads=False,
            create_private_threads=False,
            create_instant_invite=False,
            attach_files=False,
            embed_links=False,
            add_reactions=False,
            use_external_emojis=False
        )
        
        try:
            await default_role.edit(permissions=perms, reason="SafeMode Emergency Lockdown")
            await interaction.followup.send("🔒 **SERVER LOCKED DOWN.** @everyone bị hạn chế gửi tin nhắn, link, file.")
        except Exception as e:
            await interaction.followup.send(f"❌ Lỗi lockdown: {e}")

    @app_commands.command(name="unlockdown", description="Mở khóa server")
    async def unlockdown_cmd(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except Exception:
            pass

        if not await self.check_permissions(interaction):
            return
        guild = interaction.guild
        default_role = guild.default_role
        
        perms = default_role.permissions
        perms.update(
            send_messages=True,
            create_public_threads=True,
            create_private_threads=True,
            create_instant_invite=True,
            attach_files=True,
            embed_links=True,
            add_reactions=True,
            use_external_emojis=True
        )
        
        try:
            await default_role.edit(permissions=perms, reason="SafeMode Lockdown Removed")
            await interaction.followup.send("🔓 **SERVER UNLOCKED.** @everyone đã được khôi phục quyền gửi tin nhắn.")
        except Exception as e:
            await interaction.followup.send(f"❌ Lỗi unlockdown: {e}")

    @app_commands.command(name="setprotectiontime", description="Tự động bật/tắt SafeMode theo giờ")
    @app_commands.describe(start="Giờ bắt đầu (VD: 20:00)", end="Giờ kết thúc (VD: 06:00)")
    async def setprotectiontime_cmd(self, interaction: discord.Interaction, start: str, end: str):
        if not await self.check_permissions(interaction):
            return
            
        # Basic validation (HH:MM)
        try:
            datetime.strptime(start, "%H:%M")
            datetime.strptime(end, "%H:%M")
        except ValueError:
            await interaction.response.send_message("❌ Định dạng giờ không hợp lệ. Vui lòng dùng định dạng `HH:MM` (VD: 20:00).", ephemeral=True)
            return
            
        self.schedule_start = start
        self.schedule_end = end
        self.save_config()
        
        await interaction.response.send_message(f"✅ Đã thiết lập Protection Time: Bật lúc `{start}` - Tắt lúc `{end}` (Giờ VN).")

    whitelist_group = app_commands.Group(name="whitelist", description="Quản lý Anti-Nuke Whitelist")

    @whitelist_group.command(name="add", description="Thêm user vào whitelist")
    async def wl_add_cmd(self, interaction: discord.Interaction, user: discord.Member):
        if not await self.check_permissions(interaction):
            return
        self.whitelist.add(user.id)
        self.save_config()
        await interaction.response.send_message(f"✅ Đã thêm {user.mention} vào whitelist.")

    @whitelist_group.command(name="remove", description="Xóa user khỏi whitelist")
    async def wl_remove_cmd(self, interaction: discord.Interaction, user: discord.Member):
        if not await self.check_permissions(interaction):
            return
        if user.id in self.whitelist:
            self.whitelist.remove(user.id)
            self.save_config()
            await interaction.response.send_message(f"✅ Đã xóa {user.mention} khỏi whitelist.")
        else:
            await interaction.response.send_message("⚠️ User không có trong whitelist.")

    @whitelist_group.command(name="list", description="Xem danh sách whitelist")
    async def wl_list_cmd(self, interaction: discord.Interaction):
        if not self.whitelist:
            await interaction.response.send_message("📜 Whitelist trống.", ephemeral=True)
            return
            
        mentions = [f"<@{uid}>" for uid in self.whitelist]
        embed = discord.Embed(title="📜 Anti-Nuke Whitelist", description="\n".join(mentions), color=0x3498DB)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tasks.loop(minutes=1)
    async def schedule_task(self):
        if not self.schedule_start or not self.schedule_end:
            return
            
        now = datetime.now(VN_TZ).strftime("%H:%M")
        
        if now == self.schedule_start and not self.safemode_active:
            self.safemode_active = True
            self.save_config()
            print(f"[{now}] Auto SafeMode ON")
        elif now == self.schedule_end and self.safemode_active:
            self.safemode_active = False
            self.save_config()
            print(f"[{now}] Auto SafeMode OFF")

    @schedule_task.before_loop
    async def before_schedule_task(self):
        await self.bot.wait_until_ready()

    # --- ANTI-NUKE LOGIC ---

    async def check_threshold(self, user_id: int, action: str, limit: int, time_window: int) -> bool:
        """Kiểm tra xem user có vượt quá giới hạn hành động trong khoảng thời gian không."""
        now = datetime.now().timestamp()
        
        if user_id not in self.action_tracker:
            self.action_tracker[user_id] = {}
        if action not in self.action_tracker[user_id]:
            self.action_tracker[user_id][action] = []
            
        # Thêm timestamp hiện tại
        self.action_tracker[user_id][action].append(now)
        
        # Xóa các timestamp đã cũ hơn time_window
        self.action_tracker[user_id][action] = [t for t in self.action_tracker[user_id][action] if now - t <= time_window]
        
        # Nếu số lượng hành động vượt ngưỡng -> return True
        return len(self.action_tracker[user_id][action]) >= limit

    async def trigger_raid_response(self, guild: discord.Guild, user_id: int, action: str, audit_entry: discord.AuditLogEntry):
        """Xử lý khi phát hiện raid."""
        executor = guild.get_member(user_id) or await guild.fetch_member(user_id)
        
        if not executor:
            return
            
        # Bỏ qua nếu là bot hoặc owner hoặc nằm trong whitelist
        if executor.bot or executor.id == guild.owner_id or executor.id in self.whitelist:
            return
            
        # 1. Ghi log
        print(f"🚨 RAID DETECTED: {executor} performed {action}")
        
        # 2. Xử phạt: Ban thẳng tay + lưu UID (theo yêu cầu User)
        try:
            await guild.ban(executor, reason=f"Anti-Nuke: Raid Detected ({action})")
            punish_result = f"Banned {executor.mention} (ID: {executor.id})"
        except discord.Forbidden:
            punish_result = f"Failed to ban {executor.mention} (Missing Permissions)"
            
        # 3. Tự động Lockdown
        lockdown_result = "Lockdown successful"
        default_role = guild.default_role
        perms = default_role.permissions
        perms.update(send_messages=False, create_public_threads=False, create_private_threads=False, create_instant_invite=False, attach_files=False, embed_links=False, add_reactions=False, use_external_emojis=False)
        try:
            await default_role.edit(permissions=perms, reason="Auto-Lockdown by Anti-Nuke")
        except Exception as e:
            lockdown_result = f"Lockdown failed: {e}"
            
        # 4. Thông báo toàn bộ kênh
        embed = discord.Embed(title="🚨 RAID DETECTED & PREVENTED", color=discord.Color.red())
        embed.add_field(name="Executor", value=f"{executor.mention} (`{executor.id}`)", inline=False)
        embed.add_field(name="Action Triggered", value=action, inline=False)
        embed.add_field(name="Punishment", value=punish_result, inline=False)
        embed.add_field(name="Status", value=lockdown_result, inline=False)
        embed.set_footer(text="Hệ thống Anti-Nuke đã tự động bảo vệ server.")
        
        for channel in guild.text_channels:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                pass

    async def get_audit_executor(self, guild: discord.Guild, action_type: discord.AuditLogAction):
        """Lấy người thực hiện từ Audit Log."""
        if not guild.me.guild_permissions.view_audit_log:
            return None
        async for entry in guild.audit_logs(limit=1, action=action_type):
            return entry
        return None

    # --- EVENT LISTENERS ---

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not self.safemode_active: return
        entry = await self.get_audit_executor(channel.guild, discord.AuditLogAction.channel_delete)
        if entry and entry.user:
            if await self.check_threshold(entry.user.id, "channel_delete", 3, 15):
                await self.trigger_raid_response(channel.guild, entry.user.id, "CHANNEL_DELETE", entry)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if not self.safemode_active: return
        entry = await self.get_audit_executor(channel.guild, discord.AuditLogAction.channel_create)
        if entry and entry.user:
            if await self.check_threshold(entry.user.id, "channel_create", 5, 15):
                await self.trigger_raid_response(channel.guild, entry.user.id, "CHANNEL_CREATE", entry)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        if not self.safemode_active: return
        entry = await self.get_audit_executor(role.guild, discord.AuditLogAction.role_delete)
        if entry and entry.user:
            if await self.check_threshold(entry.user.id, "role_delete", 3, 15):
                await self.trigger_raid_response(role.guild, entry.user.id, "ROLE_DELETE", entry)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        if not self.safemode_active: return
        entry = await self.get_audit_executor(role.guild, discord.AuditLogAction.role_create)
        if entry and entry.user:
            if await self.check_threshold(entry.user.id, "role_create", 5, 15):
                await self.trigger_raid_response(role.guild, entry.user.id, "ROLE_CREATE", entry)

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        if not self.safemode_active: return
        entry = await self.get_audit_executor(channel.guild, discord.AuditLogAction.webhook_create)
        if entry and entry.user:
            # Note: on_webhooks_update fires for create/delete/update, we roughly map it to create if audit log shows it.
            if await self.check_threshold(entry.user.id, "webhook_create", 2, 15):
                await self.trigger_raid_response(channel.guild, entry.user.id, "WEBHOOK_CREATE", entry)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if not self.safemode_active: return
        entry = await self.get_audit_executor(guild, discord.AuditLogAction.ban)
        if entry and entry.user:
            if await self.check_threshold(entry.user.id, "mass_ban", 5, 30):
                await self.trigger_raid_response(guild, entry.user.id, "MASS_BAN", entry)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not self.safemode_active: return
        # Check if it was a kick
        entry = await self.get_audit_executor(member.guild, discord.AuditLogAction.kick)
        if entry and entry.user and entry.target.id == member.id:
            if await self.check_threshold(entry.user.id, "mass_kick", 5, 30):
                await self.trigger_raid_response(member.guild, entry.user.id, "MASS_KICK", entry)


async def setup(bot: commands.Bot):
    await bot.add_cog(SafeMode(bot))
