"""
cogs/appeals.py – Hệ thống kháng cáo cho thành viên bị xử phạt (Đồng bộ trực tiếp với Web)
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import uuid  # BẮT BUỘC PHẢI CÓ ĐỂ TẠO ID ĐƠN
from datetime import datetime

from config import cfg, COLOR_INFO, COLOR_SUCCESS, COLOR_ERROR
import utils

APPEALS_FILE = "data/appeals.json"

def load_appeals() -> dict:
    if not os.path.exists(APPEALS_FILE):
        os.makedirs(os.path.dirname(APPEALS_FILE), exist_ok=True)
        with open(APPEALS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2, ensure_ascii=False)
        return {}
    try:
        with open(APPEALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Appeals DB Error] Không thể đọc file JSON: {e}")
        return {}

def save_appeals(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(APPEALS_FILE), exist_ok=True)
        with open(APPEALS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Appeals DB Error] Không thể ghi file JSON: {e}")


class AppealModal(discord.ui.Modal, title="📝 Gửi Kháng Cáo"):
    violation = discord.ui.TextInput(
        label="Hành vi vi phạm bị xử phạt",
        placeholder="Bạn bị xử phạt vì lý do gì?",
        max_length=200,
    )
    explanation = discord.ui.TextInput(
        label="Giải trình của bạn",
        style=discord.TextStyle.paragraph,
        placeholder="Hãy giải thích tại sao bạn cho rằng mình bị xử oan...",
        max_length=1000,
    )
    case_id = discord.ui.TextInput(
        label="Case ID (nếu có)",
        placeholder="Ví dụ: #42 (để trống nếu không biết)",
        required=False,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Xử lý khi người dùng submit form kháng cáo"""
        print(f"\n[DEBUG APPEALS] === MODAL SUBMIT BẮT ĐẦU TỪ USER: {interaction.user} ({interaction.user.id}) ===")
        
        # BƯỚC 1: Phản hồi Discord ngay lập tức
        try:
            await interaction.response.defer(ephemeral=True)
            print("[DEBUG APPEALS] ✅ Defer thành công")
        except Exception as defer_err:
            print(f"[DEBUG APPEALS] ❌ Defer thất bại: {defer_err}")
            # Vẫn tiếp tục xử lý, không return

        try:
            # Tạo mã đơn và thời gian
            appeal_id = str(uuid.uuid4())[:8]
            now_iso = datetime.utcnow().isoformat()
            
            print(f"[DEBUG APPEALS] Tạo appeal_id: {appeal_id}")

            # BƯỚC 2: GHI THẲNG VÀO DB JSON
            db = load_appeals()
            print(f"[DEBUG APPEALS] Đã load DB, hiện có {len(db)} đơn")

            db[appeal_id] = {
                "id": appeal_id,
                "user_id": str(interaction.user.id),
                "username": interaction.user.name,
                "user_avatar": interaction.user.display_avatar.url if interaction.user.display_avatar else "",
                "violation": self.violation.value,
                "explanation": self.explanation.value,
                "case_id": self.case_id.value or "",
                "status": "pending",
                "thread_id": None,
                "created_at": now_iso,
                "messages": [
                    {
                        "sender": "appellant",
                        "sender_name": interaction.user.display_name,
                        "content": f"[Đơn gốc Discord] Lý do: {self.violation.value}\nGiải trình: {self.explanation.value}",
                        "timestamp": now_iso
                    }
                ]
            }
            
            save_appeals(db)
            print(f"🎉 [DEBUG APPEALS] ĐÃ GHI THÀNH CÔNG ĐƠN [{appeal_id}] VÀO FILE: {APPEALS_FILE}")

            # BƯỚC 3: XỬ LÝ DISCORD (gửi embed + thread)
            guild = interaction.guild
            channel_id = int(cfg.appeal_channel_id) if cfg.appeal_channel_id else None
            appeal_ch = guild.get_channel(channel_id) if (guild and channel_id) else None
            thread_id = None

            if appeal_ch:
                try:
                    embed = discord.Embed(
                        title="📨 Kháng Cáo Mới",
                        description=f"Thành viên {interaction.user.mention} gửi kháng cáo.",
                        color=COLOR_INFO,
                    )
                    embed.add_field(name="Vi phạm bị xử phạt", value=self.violation.value, inline=False)
                    embed.add_field(name="Giải trình", value=self.explanation.value, inline=False)
                    embed.add_field(name="Case ID", value=self.case_id.value or "Không cung cấp", inline=True)
                    embed.add_field(name="Người dùng", value=f"{interaction.user} (`{interaction.user.id}`)", inline=True)
                    if interaction.user.display_avatar:
                        embed.set_thumbnail(url=interaction.user.display_avatar.url)
                    embed.set_footer(text=f"Mã đơn: {appeal_id}")

                    view = AppealActionView(appeal_id, interaction.user.id)
                    main_msg = await appeal_ch.send(embed=embed, view=view)

                    # Tạo Thread
                    try:
                        thread = await main_msg.create_thread(
                            name=f"kháng-cáo-{interaction.user.name}",
                            auto_archive_duration=4320
                        )
                        thread_id = str(thread.id)
                        await thread.send(f"💬 Kênh chat trực tuyến đồng bộ với Web dành cho ca kháng cáo của {interaction.user.mention}.")
                        
                        # Cập nhật thread_id vào DB
                        db = load_appeals()
                        if appeal_id in db:
                            db[appeal_id]["thread_id"] = thread_id
                            save_appeals(db)
                        print(f"[DEBUG APPEALS] Đã tạo thread ID: {thread_id}")
                    except Exception as thread_err:
                        print(f"[DEBUG APPEALS] Không thể tạo Thread: {thread_err}")
                except Exception as discord_err:
                    print(f"[DEBUG APPEALS] Lỗi gửi tin nhắn Discord: {discord_err}")
            else:
                print(f"[DEBUG APPEALS] Không tìm thấy kênh appeal ID: {cfg.appeal_channel_id}")

            # BƯỚC 4: Phản hồi cho người dùng
            await interaction.followup.send(
                embed=utils.mod_embed(
                    "✅ Gửi đơn thành công",
                    f"Kháng cáo của bạn (Mã đơn: `{appeal_id}`) đã được ghi nhận.\n"
                    "Bạn có thể kiểm tra trạng thái trên Web.",
                    COLOR_SUCCESS,
                ),
                ephemeral=True,
            )
            print(f"[DEBUG APPEALS] Hoàn tất xử lý đơn {appeal_id}")

        except Exception as e:
            import traceback
            print("[DEBUG APPEALS] ❌ LỖI NẶNG KHI XỬ LÝ ĐƠN:")
            traceback.print_exc()
            
            # Phản hồi lỗi cho user
            try:
                await interaction.followup.send(
                    embed=utils.mod_embed(
                        "❌ Lỗi hệ thống",
                        "Đã xảy ra lỗi khi gửi kháng cáo. Vui lòng thử lại sau.",
                        COLOR_ERROR,
                    ),
                    ephemeral=True,
                )
            except:
                pass


class AppealActionView(discord.ui.View):
    """View nút Chấp nhận / Từ chối kháng cáo cho Staff (Có đồng bộ DB Web)."""

    def __init__(self, appeal_id: str, appellant_id: int) -> None:
        super().__init__(timeout=None)
        self.appeal_id = appeal_id
        self.appellant_id = appellant_id

    @discord.ui.button(label="✅ Chấp nhận", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try: await interaction.response.defer(ephemeral=True)
        except Exception: pass

        if not utils.is_mod(interaction.user):
            await interaction.followup.send("❌ Chỉ Moderator mới có thể xử lý kháng cáo.", ephemeral=True)
            return

        db = load_appeals()
        if self.appeal_id in db:
            db[self.appeal_id]["status"] = "accepted"
            db[self.appeal_id]["messages"].append({
                "sender": "staff",
                "sender_name": "Hệ thống",
                "content": f"✅ Đơn kháng cáo đã được **Chấp nhận** bởi Moderator {interaction.user.display_name}.",
                "timestamp": datetime.utcnow().isoformat()
            })
            save_appeals(db)

        user = interaction.guild.get_member(self.appellant_id)
        if user:
            try:
                await user.send(
                    embed=utils.mod_embed(
                        "✅ Kháng cáo được chấp nhận",
                        "Ban quản trị đã xem xét và chấp nhận kháng cáo của bạn.\n"
                        "Xử phạt của bạn đã được gỡ bỏ (nếu có). Chào mừng trở lại!",
                        COLOR_SUCCESS,
                    )
                )
            except discord.HTTPException: pass

        embed = interaction.message.embeds[0]
        embed.color = COLOR_SUCCESS
        embed.set_footer(text=f"✅ Chấp nhận bởi {interaction.user} | ID: {self.appeal_id}")
        await interaction.message.edit(embed=embed, view=None)
        await interaction.followup.send("✅ Đã cập nhật trạng thái Chấp nhận lên Web.", ephemeral=True)

    @discord.ui.button(label="❌ Từ chối", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        try: await interaction.response.defer(ephemeral=True)
        except Exception: pass

        if not utils.is_mod(interaction.user):
            await interaction.followup.send("❌ Chỉ Moderator mới có thể xử lý kháng cáo.", ephemeral=True)
            return

        db = load_appeals()
        if self.appeal_id in db:
            db[self.appeal_id]["status"] = "rejected"
            db[self.appeal_id]["messages"].append({
                "sender": "staff",
                "sender_name": "Hệ thống",
                "content": f"❌ Đơn kháng cáo đã bị **Từ chối** bởi Moderator {interaction.user.display_name}.",
                "timestamp": datetime.utcnow().isoformat()
            })
            save_appeals(db)

        user = interaction.guild.get_member(self.appellant_id)
        if user:
            try:
                await user.send(
                    embed=utils.mod_embed(
                        "❌ Kháng cáo bị từ chối",
                        "Ban quản trị đã xem xét kháng cáo của bạn và quyết định giữ nguyên hình phạt.",
                        COLOR_ERROR,
                    )
                )
            except discord.HTTPException: pass

        embed = interaction.message.embeds[0]
        embed.color = COLOR_ERROR
        embed.set_footer(text=f"❌ Từ chối bởi {interaction.user} | ID: {self.appeal_id}")
        await interaction.message.edit(embed=embed, view=None)
        await interaction.followup.send("❌ Đã cập nhật trạng thái Từ chối lên Web.", ephemeral=True)


class Appeals(commands.Cog):
    """Hệ thống kháng cáo."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="appeal", description="Gửi kháng cáo lên ban quản trị")
    async def appeal_slash(self, interaction: discord.Interaction) -> None:
        """Kích hoạt và hiển thị Modal Kháng Cáo chuẩn xác."""
        print(f"[DEBUG APPEALS] Lệnh /appeal được dùng bởi {interaction.user} ({interaction.user.id})")
        
        try:
            # Tạo modal NGAY LẬP TỨC, không làm gì thừa trước đó
            await interaction.response.send_modal(AppealModal())
            print("[DEBUG APPEALS] Đã gửi Modal thành công (trong < 3s)")
            
        except discord.HTTPException as e:
            if e.code == 40060:
                print("[DEBUG APPEALS] 40060 - Interaction already responded")
                return
            elif e.code == 10062:
                print("[DEBUG APPEALS] 10062 - Unknown interaction (timeout)")
                # Không thể cứu được nữa vì interaction đã chết
                return
            else:
                print(f"[DEBUG APPEALS] HTTP Error: {e}")
                raise
        except Exception as e:
            print(f"[DEBUG APPEALS] Lỗi không xác định: {e}")
            import traceback
            traceback.print_exc()
#####################################################################
    @commands.command(name="appeal")
    async def appeal_prefix(self, ctx: commands.Context) -> None:
        await ctx.send(
            embed=utils.mod_embed(
                "📝 Hướng dẫn kháng cáo",
                "Dùng lệnh **slash** `/appeal` để mở form kháng cáo trực tiếp trên Discord.\n"
                "Hoặc truy cập trang web để gửi kháng cáo trực tuyến.",
                COLOR_INFO,
            )
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Đồng bộ tin nhắn chat từ Thread Discord về Web."""
        if message.author.bot:
            return

        if not isinstance(message.channel, discord.Thread):
            return

        thread_id = str(message.channel.id)
        db = load_appeals()

        matched_id = None
        for appeal_id, appeal in db.items():
            if appeal.get("thread_id") == thread_id:
                matched_id = appeal_id
                break

        if not matched_id:
            return

        if db[matched_id].get("status") == "closed":
            return

        is_appellant = str(message.author.id) == db[matched_id]["user_id"]
        sender_role = "appellant" if is_appellant else "staff"

        msg_entry = {
            "sender": sender_role,
            "sender_name": message.author.display_name,
            "content": message.content,
            "timestamp": message.created_at.isoformat()
        }
        db[matched_id]["messages"].append(msg_entry)
        save_appeals(db)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Appeals(bot))