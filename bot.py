"""
bot.py – Entry point chính của Discord Moderation Bot
"""
from __future__ import annotations

import asyncio
import os
import sys
import logging

import discord
from discord.ext import commands
from discord import app_commands

from config import cfg, COLOR_ERROR, TOKEN

# ─── Logging setup ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)

log = logging.getLogger("bot")


# =========================
# MODULE DEBUG
# =========================

def dump_modules():
    print("\n" + "=" * 60)
    print("[BOT MODULES LOADED]")
    for name in sorted(sys.modules.keys()):
        if "cogs" in name or "discord" in name:
            print(f" - {name}")
    print("=" * 60 + "\n")
# ─── Intents ─────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members          = True
intents.guilds           = True
intents.moderation       = True
intents.presences        = True  # Cho phép đọc trạng thái online, game, Spotify

# ─── Bot setup ───────────────────────────────────────────────────────────────

class ModerationBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=cfg.bot_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )

     # =========================
    # LOAD COGS
    # =========================

    async def setup_hook(self) -> None:
        cogs = [
            "cogs.guardbot",
            "cogs.moderation",
            "cogs.rules",
            "cogs.appeals",
            "cogs.logging_events",
            "cogs.config_cmd",
            "cogs.safemode",
            "cogs.online",
            "cogs.terminal",
            "cogs.AI_chat",
        ]

        # 1. Dọn dẹp các lệnh global cũ trên Discord (sync một tree trống trước khi load cogs)
        try:
            if cfg.guild_id:
                await self.tree.sync()
                log.info("🧹 Đã dọn dẹp các lệnh global cũ trên Discord")
        except Exception as e:
            log.error(f"❌ Lỗi khi dọn dẹp lệnh global: {e}")

        # 2. Load cogs (thêm lệnh vào bộ nhớ)
        for cog in cogs:
            try:
                await self.load_extension(cog)
                log.info(f"✅ Loaded cog: {cog}")
            except Exception as e:
                log.error(f"❌ Lỗi load cog {cog}: {e}")

        # persistent views
        try:
            from cogs.moderation import ProposalView
            self.add_view(ProposalView())
        except Exception as e:
            log.error(f"❌ View error: {e}")

        # 3. Sync slash commands vào Guild
        try:
            if cfg.guild_id:
                guild = discord.Object(id=cfg.guild_id)
                self.tree.clear_commands(guild=guild)
                self.tree.copy_global_to(guild=guild)

                synced = await self.tree.sync(guild=guild)
                log.info(f"✅ Synced {len(synced)} commands (guild)")
            else:
                synced = await self.tree.sync()
                log.info(f"✅ Synced {len(synced)} commands (global)")
        except Exception as e:
            log.error(f"❌ Sync error: {e}")

        # MODULE DUMP (QUAN TRỌNG)
        dump_modules()

    # async def on_ready(self) -> None:
    #     log.info(f"🤖 Bot đã online: {self.user} (ID: {self.user.id})")
    #     log.info(f"📡 Kết nối {len(self.guilds)} server(s)")

    #     await self.change_presence(
    #         activity=discord.Activity(
    #             type=discord.ActivityType.watching,
    #             name=f"nội quy server | {cfg.bot_prefix}help",
    #         ),
    #         status=discord.Status.online,
    #     )

    #     # Gửi setup wizard nếu chưa cấu hình channels/roles
    #     await self._check_setup()
    async def on_ready(self):
                log.info(f"🤖 Bot online: {self.user} ({self.user.id})")
                log.info(f"📡 Servers: {len(self.guilds)}")

                dump_modules()

                await self.change_presence(
                    activity=discord.Activity(
                        type=discord.ActivityType.watching,
                        name=f"nội quy server | {cfg.bot_prefix}help",
                    ),
                    status=discord.Status.online,
                )     
    async def _check_setup(self) -> None:
        """
        Kiểm tra xem bot đã được cấu hình chưa.
        Nếu chưa → DM owner server hoặc gửi vào kênh đầu tiên tìm được.
        """
        missing_channels = []
        missing_roles    = []

        if not cfg.mod_log_channel_id:
            missing_channels.append("📋 **Mod Log** (`/config channel mod_log #kênh`)")
        if not cfg.rules_channel_id:
            missing_channels.append("📜 **Rules** (`/config channel rules #kênh`)")
        if not cfg.appeal_channel_id:
            missing_channels.append("📝 **Appeal** (`/config channel appeal #kênh`)")
        if not cfg.mod_role_id:
            missing_roles.append("👮 **Moderator** (`/config role moderator @role`)")
        if not cfg.admin_role_id:
            missing_roles.append("🛡️ **Admin** (`/config role admin @role`)")
        if not cfg.muted_role_id:
            missing_roles.append("🔇 **Muted** (`/config role muted @role`)")

        if not missing_channels and not missing_roles:
            log.info("✅ Cấu hình đầy đủ, bot sẵn sàng hoạt động.")
            return

        log.warning("⚠️ Bot chưa được cấu hình đầy đủ – đang gửi setup guide...")

        embed = discord.Embed(
            title="🛠️ Cần Cấu Hình Bot",
            description=(
                "Bot vừa khởi động nhưng **chưa được cấu hình đầy đủ**.\n"
                "Dùng các lệnh `/config` dưới đây để hoàn tất. "
                "Sau khi xong, bot sẽ hoạt động bình thường.\n\n"
                "*Chỉ Admin mới thấy thông báo này.*"
            ),
            color=0xF39C12,
        )

        if missing_channels:
            embed.add_field(
                name="📺 Kênh chưa gán",
                value="\n".join(missing_channels),
                inline=False,
            )
        if missing_roles:
            embed.add_field(
                name="👤 Role chưa gán",
                value="\n".join(missing_roles),
                inline=False,
            )

        embed.add_field(
            name="💡 Cách nhanh nhất",
            value=(
                "Gõ `/config channel` để gán kênh\n"
                "Gõ `/config role` để gán role\n"
                "Gõ `/config view` để xem tổng quan"
            ),
            inline=False,
        )
        embed.set_footer(text="Thông báo này sẽ không xuất hiện lại khi đã cấu hình đủ.")

        # Thử DM owner trước
        for guild in self.guilds:
            sent = False

            # Ưu tiên DM owner server
            try:
                owner = guild.owner
                if owner:
                    await owner.send(embed=embed)
                    log.info(f"📩 Đã gửi setup guide cho owner {owner} ({guild.name})")
                    sent = True
            except discord.HTTPException:
                pass

            # Fallback: gửi vào kênh đầu tiên bot có quyền gửi
            if not sent:
                for ch in guild.text_channels:
                    try:
                        perms = ch.permissions_for(guild.me)
                        if perms.send_messages and perms.embed_links:
                            await ch.send(embed=embed)
                            log.info(f"📩 Đã gửi setup guide vào #{ch.name} ({guild.name})")
                            break
                    except discord.HTTPException:
                        continue

    # async def on_command_error(self, ctx: commands.Context,
    #                             error: commands.CommandError) -> None:
    #     if isinstance(error, commands.HybridCommandError):
    #         error = error.original

    #     if isinstance(error, commands.CommandNotFound):
    #         return

    #     embed = None
    #     if isinstance(error, commands.MissingRequiredArgument):
    #         embed = discord.Embed(
    #             title="❌ Thiếu tham số",
    #             description=f"Thiếu: `{error.param.name}`\nDùng `{cfg.bot_prefix}help {ctx.command}` để xem hướng dẫn.",
    #             color=COLOR_ERROR,
    #         )
    #     elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound, commands.BadArgument)):
    #         embed = discord.Embed(
    #             title="❌ Không tìm thấy thành viên",
    #             description="Vui lòng @mention hoặc nhập ID / Username chính xác của thành viên.",
    #             color=COLOR_ERROR,
    #         )
    #     elif isinstance(error, commands.CheckFailure):
    #         pass
    #     else:
    #         log.error(f"Command error in {ctx.command}: {error}")
    #         embed = discord.Embed(
    #             title="❌ Lỗi",
    #             description=f"Đã xảy ra lỗi: `{error}`",
    #             color=COLOR_ERROR,
    #         )

    #     if embed:
    #         try:
    #             if ctx.interaction:
    #                 if ctx.interaction.response.is_done():
    #                     await ctx.interaction.followup.send(
    #                         embed=embed,
    #                         ephemeral=True
    #                     )
    #                 else:
    #                     await ctx.interaction.response.send_message(
    #                         embed=embed,
    #                         ephemeral=True
    #                     )
    #             else:
    #                 await ctx.send(embed=embed)

    #         except Exception as e:
    #             log.error(f"Error while sending error message: {e}")

    # ─── Help command ────────────────────────────────────────────────────────
    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError
    ) -> None:

        # =========================
        # UNWRAP HYBRID ERROR SAFE
        # =========================
        if isinstance(error, commands.HybridCommandError):
            error = getattr(error, "original", error)

        # =========================
        # IGNORE NOT FOUND
        # =========================
        if isinstance(error, commands.CommandNotFound):
            return

        # =========================
        # LOG FULL CONTEXT (IMPORTANT)
        # =========================
        log.error(
            f"[COMMAND ERROR] "
            f"cmd={getattr(ctx.command, 'name', None)} "
            f"user={ctx.author} "
            f"guild={getattr(ctx.guild, 'name', None)} "
            f"error={repr(error)}"
        )

        embed = None

        # =========================
        # USER ERRORS
        # =========================

        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Thiếu tham số",
                description=(
                    f"Thiếu: `{error.param.name}`\n"
                    f"Dùng `{cfg.bot_prefix}help {ctx.command}` để xem hướng dẫn."
                ),
                color=COLOR_ERROR,
            )

        # Kiểm tra cực kỳ chặt chẽ: Chỉ báo "Không tìm thấy" nếu thực sự lỗi do tìm kiếm User/Member thất bại TRƯỚC KHI lệnh chạy
        elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            embed = discord.Embed(
                title="❌ Không tìm thấy người dùng",
                description="Mention hoặc ID sai rồi, bot không đọc được suy nghĩ con người đâu 😏",
                color=COLOR_ERROR,
            )

        elif isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="❌ Đối số không hợp lệ",
                description="Tham số bạn truyền vào không đúng kiểu dữ liệu yêu cầu.",
                color=COLOR_ERROR,
            )

        elif isinstance(error, commands.CheckFailure):
            log.warning(f"[CHECK FAILED] user={ctx.author} cmd={ctx.command}")
            return

        # Bỏ qua hoặc phân tách riêng TransformerError của AppCommand ra, tránh bị nhận vơ thành lỗi Unban
        elif "TransformerError" in repr(error) or "CommandInvokeError" in repr(error):
            # Nếu lệnh unban đã chạy và bạn biết nó unban được, tức là lỗi này chỉ là lỗi phản hồi UI của Discord.
            # Ta sẽ kiểm tra nếu lệnh là unban thì không in lỗi ảo này ra nữa.
            if getattr(ctx.command, 'name', None) == 'unban':
                log.info("[ERROR HANDLER] Bỏ qua lỗi phản hồi ảo của lệnh unban.")
                return
            
            embed = discord.Embed(
                title="❌ Lỗi thực thi lệnh",
                description="Discord không kịp phản hồi hoặc lệnh nhập sai định dạng.",
                color=COLOR_ERROR,
            )

        else:
            embed = discord.Embed(
                title="❌ Lỗi hệ thống",
                description=f"`{error}`",
                color=COLOR_ERROR,
            )

        # =========================
        # SEND ERROR (SAFE INTERACTION HANDLING)
        # =========================

        if not embed:
            return

        try:
            if hasattr(ctx, "interaction") and ctx.interaction:
                # Kiểm tra cả webhook hoàn thành hoặc trạng thái phản hồi để chọn cách gửi phù hợp
                if ctx.interaction.response.is_done() or ctx.interaction.command_failed:
                    try:
                        await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                    except Exception:
                        # Nếu followup vẫn tịt ngòi (do interaction chết hẳn), gửi thẳng qua channel bằng ctx.send
                        await ctx.send(embed=embed)
                else:
                    try:
                        await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
                    except discord.HTTPException as he:
                        # Bắt lỗi code 40060 hoặc lỗi tương tự khi Discord từ chối response_message
                        if he.code == 40060:
                            try:
                                await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                            except Exception:
                                await ctx.send(embed=embed)
                        else:
                            await ctx.send(embed=embed)
            else:
                await ctx.send(embed=embed)

        except Exception as e:
            log.error(f"[ERROR HANDLER FAIL] {e}")
    @commands.command(name="help", aliases=["h", "trợgiúp"])
    async def help_cmd(self, ctx: commands.Context) -> None:
        embed = discord.Embed(
            title="🤖 Hướng Dẫn Sử Dụng Bot",
            description=f"Prefix: `{cfg.bot_prefix}` | Slash: `/`",
            color=0x3498DB,
        )
        embed.add_field(name="📋 Thành viên", value=(
            "`/guardbot rules` – Xem nội quy\n"
            "`/guardbot staffrules` – Nội quy Ban Quản Trị\n"
            "`/guardbot appeal` – Gửi kháng cáo\n"
            "`/guardbot case [id]` – Xem case"
        ), inline=False)
        embed.add_field(name="⚖️ Staff", value=(
            "`/guardbot warn` `/guardbot mute` `/guardbot unmute` `/guardbot kick` `/guardbot ban` `/guardbot unban`\n"
            "`/guardbot warns` `/guardbot clearwarns` `/guardbot purge`"
        ), inline=False)
        embed.add_field(name="🛡️ Admin", value=(
            "`/guardbot config view` – Xem & chỉnh cấu hình\n"
            "`/guardbot config channel` – Gán kênh\n"
            "`/guardbot config role` – Gán role\n"
            "`/guardbot config warn` – Đổi hình phạt\n"
            "`/guardbot config addword` / `removeword` – Quản lý từ cấm\n"
            "`/guardbot config set` – Đổi ngưỡng spam/emoji...\n"
            "`/guardbot postrules` – Đăng nội quy\n"
            "`/guardbot poststaffrules` – Đăng nội quy staff"
        ), inline=False)
        embed.set_footer(text="Auto-mod: Spam | Link | Quảng cáo | Thù ghét | Chính trị")
        await ctx.send(embed=embed)


# ─── Main ────────────────────────────────────────────────────────────────────

# ─── KHỞI CHẠY ĐỒNG BỘ BACKEND FASTAPI & DISCORD BOT ──────────────────────────

async def main() -> None:
    if not TOKEN:
        log.error("❌ Chưa có DISCORD_TOKEN!")
        sys.exit(1)

    # 1. Khởi tạo đối tượng Bot độc lập
    bot = ModerationBot()

    # 2. Tự động tìm và import biến "app" từ file chạy Web của bạn
    try:
        from web.main import app as fastapi_app  # Thử tìm trong file main.py
    except ImportError:
        try:
            from app import app as fastapi_app  # Nếu không có, thử tìm trong app.py
        except ImportError:
            log.error("❌ Không tìm thấy file khai báo FastAPI (app/main). Vui lòng kiểm tra lại cấu trúc file!")
            sys.exit(1)

    # 🌟 CẦU NỐI ĐỒNG BỘ: Gán app vào bot để Cog Discord đọc được app.state
    bot.app = fastapi_app
    fastapi_app.state.terminal_session = None  # Khởi tạo tránh lỗi trống bộ nhớ ban đầu

    # 3. Cấu hình cổng chạy cho Web Server (Port 8000 hoặc port hiện tại của web bạn)
    import uvicorn
    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)

    # Đút cả 2 luồng Web Backend và Discord Bot vào chạy song song không block nhau
    await asyncio.gather(
        server.serve(),  # Luồng 1: Chạy Web API
        bot.start(TOKEN) # Luồng 2: Chạy Discord Bot
    )

if __name__ == "__main__":
    asyncio.run(main())
