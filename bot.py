"""
bot.py – Entry point chính của Discord Moderation Bot
"""
from __future__ import annotations

import sys
import logging

import discord
from discord.ext import commands

from config import cfg, COLOR_ERROR, TOKEN

# ─── Logging ─────────────────────────────────────────────

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


# ─── Debug modules ───────────────────────────────────────

def dump_modules():
    print("\n" + "=" * 60)
    print("[BOT MODULES LOADED]")
    for name in sorted(sys.modules.keys()):
        if "cogs" in name or "discord" in name:
            print(f" - {name}")
    print("=" * 60 + "\n")


# ─── Intents ─────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.moderation = True


# ─── Bot Class ───────────────────────────────────────────

class ModerationBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=cfg.bot_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
        )

    # =========================
    # LOAD COGS
    # =========================
    async def setup_hook(self):
        cogs = [
            "cogs.automod",
            "cogs.moderation",
            "cogs.rules",
            "cogs.appeals",
            "cogs.logging_events",
            "cogs.config_cmd",
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                log.info(f"✅ Loaded cog: {cog}")
            except Exception as e:
                log.error(f"❌ Cog error {cog}: {e}")

        # Views
        try:
            from cogs.moderation import ProposalView
            self.add_view(ProposalView())
        except Exception as e:
            log.error(f"❌ View error: {e}")

        # Sync slash commands
        try:
            if cfg.guild_id:
                guild = discord.Object(id=cfg.guild_id)
                self.tree.clear_commands(guild=guild)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
            else:
                synced = await self.tree.sync()

            log.info(f"✅ Synced {len(synced)} commands")

        except Exception as e:
            log.error(f"❌ Sync error: {e}")

        dump_modules()

    # =========================
    # READY EVENT (ONLY ONE)
    # =========================
    async def on_ready(self):
        log.info(f"🤖 Bot online: {self.user}")
        log.info(f"📡 Servers: {len(self.guilds)}")

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"nội quy server | {cfg.bot_prefix}help",
            ),
        )


    # =========================
    # ERROR HANDLER
    # =========================
    async def on_command_error(self, ctx, error):

        if isinstance(error, commands.HybridCommandError):
            error = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            return

        log.error(
            f"[CMD ERROR] cmd={getattr(ctx.command,'name',None)} "
            f"user={ctx.author} guild={ctx.guild} error={repr(error)}"
        )

        embed = None

        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Thiếu tham số",
                description=f"Thiếu `{error.param.name}`",
                color=COLOR_ERROR,
            )

        elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            embed = discord.Embed(
                title="❌ Không tìm thấy user",
                description="Sai mention / ID",
                color=COLOR_ERROR,
            )

        elif isinstance(error, commands.CheckFailure):
            return

        else:
            embed = discord.Embed(
                title="❌ Lỗi hệ thống",
                description=str(error),
                color=COLOR_ERROR,
            )

        try:
            if hasattr(ctx, "interaction") and ctx.interaction:
                if ctx.interaction.response.is_done():
                    await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx.send(embed=embed)

        except Exception as e:
            log.error(f"❌ Send error fail: {e}")


    # =========================
    # HELP COMMAND
    # =========================
    @commands.command(name="help", aliases=["h", "trợgiúp"])
    async def help_cmd(self, ctx):
        embed = discord.Embed(
            title="🤖 Bot Help",
            description=f"Prefix: `{cfg.bot_prefix}`",
            color=0x3498DB,
        )

        embed.add_field(
            name="📋 Member",
            value="`/appeal` `/rules` `/case`",
            inline=False,
        )

        embed.add_field(
            name="⚖️ Staff",
            value="warn / mute / ban / kick",
            inline=False,
        )

        embed.set_footer(text="AutoMod active")

        await ctx.send(embed=embed)


# ─── ENTRY POINT ─────────────────────────────────────────

def main():
    if not TOKEN:
        log.error("❌ Missing TOKEN")
        sys.exit(1)

    bot = ModerationBot()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()