"""
cogs/guardbot.py
Group chính của GuardBot
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class GuardBot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Group gốc
    guardbot = app_commands.Group(
        name="guardbot",
        description="GuardBot Security System"
    )

    @guardbot.command(
        name="info",
        description="Thông tin GuardBot"
    )
    async def info(
        self,
        interaction: discord.Interaction
    ):
        guild = interaction.guild

        humans = len([m for m in guild.members if not m.bot])
        bots = len([m for m in guild.members if m.bot])

        embed = discord.Embed(
            title="🛡️ GuardBot Security Center",
            description=(
                "Hệ thống quản lý và kiểm duyệt server.\n\n"
                "• Moderation\n"
                "• Appeals\n"
                "• Staff Proposals\n"
                "• Case Logging\n"
                "• Statistics"
            ),
            color=0x2F3136
        )

        embed.add_field(
            name="📊 Thống kê",
            value=(
                f"👥 Người dùng: **{humans}**\n"
                f"🤖 Bot: **{bots}**\n"
                f"🎭 Role: **{len(guild.roles)}**"
            ),
            inline=False
        )

        embed.set_footer(
            text="GuardBot v3.0"
        )

        await interaction.response.send_message(
            embed=embed
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(
        GuardBot(bot)
    )