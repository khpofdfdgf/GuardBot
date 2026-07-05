"""
cogs/logging_events.py – Ghi log các sự kiện server (join, leave, edit, delete)
"""
from __future__ import annotations

from datetime import timezone

import discord
from discord.ext import commands

from config import cfg, COLOR_SUCCESS, COLOR_WARN, COLOR_INFO
import utils


class Logging(commands.Cog):
    """Ghi log sự kiện quan trọng vào kênh mod-log."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        ch = guild.get_channel(cfg.mod_log_channel_id)
        if ch:
            await ch.send(embed=embed)

    def write_log(self, event_type: str, details: str) -> None:
        import os
        from datetime import datetime, timezone
        os.makedirs("data", exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        with open("data/server.log", "a", encoding="utf-8") as f:
            f.write(f"[{now}] [{event_type}] {details}\n")

    # ─── Thành viên vào/ra ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        embed = discord.Embed(
            title="📥 Thành viên mới tham gia",
            description=f"{member.mention} (`{member.id}`)",
            color=COLOR_SUCCESS,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Tên", value=str(member), inline=True)
        embed.add_field(
            name="Tài khoản tạo lúc",
            value=discord.utils.format_dt(member.created_at, "R"),
            inline=True,
        )
        embed.set_footer(text=f"Tổng thành viên: {member.guild.member_count}")
        await self._log(member.guild, embed)
        self.write_log("JOIN", f"{member} ({member.id}) joined. Total members: {member.guild.member_count}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        embed = discord.Embed(
            title="📤 Thành viên rời server",
            description=f"{member.mention} (`{member.id}`)",
            color=COLOR_WARN,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Tên", value=str(member), inline=True)
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        if roles:
            embed.add_field(name="Roles", value=" ".join(roles[-5:]), inline=True)
        await self._log(member.guild, embed)
        self.write_log("LEAVE", f"{member} ({member.id}) left the server.")

    # ─── Tin nhắn bị xóa ─────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if not message.content:
            return

        embed = discord.Embed(
            title="🗑️ Tin nhắn bị xóa",
            description=f"Trong {message.channel.mention}",
            color=COLOR_WARN,
        )
        embed.add_field(name="Tác giả", value=f"{message.author.mention}", inline=True)
        embed.add_field(
            name="Nội dung",
            value=f"```{message.content[:500]}```",
            inline=False,
        )
        await self._log(message.guild, embed)
        self.write_log("MSG_DELETE", f"Author: {message.author} ({message.author.id}) in #{message.channel.name} - Content: {message.content[:200]}")

    # ─── Tin nhắn bị chỉnh sửa ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message,
                               after: discord.Message) -> None:
        if before.author.bot or not before.guild:
            return
        if before.content == after.content:
            return

        embed = discord.Embed(
            title="✏️ Tin nhắn bị chỉnh sửa",
            description=f"Trong {before.channel.mention} | [Xem tin nhắn]({after.jump_url})",
            color=COLOR_INFO,
        )
        embed.add_field(name="Tác giả", value=f"{before.author.mention}", inline=True)
        embed.add_field(
            name="Trước",
            value=f"```{before.content[:400]}```",
            inline=False,
        )
        embed.add_field(
            name="Sau",
            value=f"```{after.content[:400]}```",
            inline=False,
        )
        await self._log(before.guild, embed)
        self.write_log("MSG_EDIT", f"Author: {before.author} ({before.author.id}) in #{before.channel.name} - Before: {before.content[:100]} | After: {after.content[:100]}")

    # ─── Thành viên bị timeout ───────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member,
                                after: discord.Member) -> None:
        # Phát hiện timeout mới
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until:
                embed = discord.Embed(
                    title="🔇 Thành viên bị timeout",
                    color=COLOR_WARN,
                )
                embed.add_field(name="Người dùng", value=str(after), inline=True)
                embed.add_field(
                    name="Hết hạn",
                    value=discord.utils.format_dt(after.timed_out_until, "R"),
                    inline=True,
                )
                await self._log(after.guild, embed)
                self.write_log("TIMEOUT", f"{after} ({after.id}) was timed out until {after.timed_out_until}")
            else:
                embed = discord.Embed(
                    title="🔊 Thành viên được bỏ timeout",
                    description=str(after),
                    color=COLOR_SUCCESS,
                )
                await self._log(after.guild, embed)
                self.write_log("UNTIMEOUT", f"{after} ({after.id}) timeout was removed.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Logging(bot))
