"""
cogs/terminal.py
Cog xử lý Slash Command lấy thông tin xác thực Web Terminal động từ FastAPI Server Memory.
Đồng bộ hoàn chỉnh theo cấu hình lưu trữ bot.app của hệ thống.
"""

import discord
from discord import app_commands
from discord.ext import commands


class TerminalCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="terminal", 
        description="Lấy thông tin tài khoản và mật khẩu động để đăng nhập Web Terminal"
    )
    @app_commands.describe(action="Chọn 'cred' để trích xuất thông tin đăng nhập bảo mật")
    @app_commands.choices(action=[
        app_commands.Choice(name="cred", value="cred")
    ])
    async def terminal_cmd(self, interaction: discord.Interaction, action: str):
        # 1. Bảo mật: Chỉ cho phép người dùng có quyền Administrator (Admin tối cao) chạy lệnh
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Bạn không có quyền hạn quản trị viên (Administrator) để sử dụng lệnh này!", 
                ephemeral=True
            )
            return

        if action == "cred":
            # 2. Truy xuất Object FastAPI App thông qua liên kết lưu trữ trong Bot state
            # Đồng bộ theo thuộc tính self.bot.app như cấu hình hệ thống hiện tại của bạn
            fastapi_app = getattr(self.bot, "app", None)
            session_data = getattr(fastapi_app.state, "terminal_session", None) if fastapi_app else None

            # Nếu chưa bấm nút "Khởi Tạo Phiên" trên giao diện Web hoặc phiên trống
            if not session_data or not session_data.get("password"):
                await interaction.response.send_message(
                    "⚠️ **Hiện tại hệ thống Web Terminal đang ở trạng thái Tắt (Offline).**\n"
                    "Vui lòng truy cập trang Web, nhấn nút **🔑 Khởi Tạo Phiên Mới** trước rồi quay lại gọi lệnh này nhé!", 
                    ephemeral=True
                )
                return

            # 3. Tạo giao diện Embed gửi thông tin đăng nhập tuyệt mật dạng Ephemeral (Chỉ mình bạn nhìn thấy)
            embed = discord.Embed(
                title="🔒 THÔNG TIN XÁC THỰC LINUX WEB TERMINAL", 
                description="Dữ liệu tài khoản động bảo mật cao, hết hạn sau 1 ngày hoặc khi huỷ phiên.",
                color=discord.Color.from_rgb(99, 102, 241) # Đồng bộ màu Indigo của giao diện Web
            )
            embed.add_field(name="👤 Tài khoản hệ thống", value=f"`{session_data['username']}`", inline=False)
            embed.add_field(name="🔑 Mật khẩu phiên động", value=f"`{session_data['password']}`", inline=False)
            embed.add_field(name="🌐 Địa chỉ cổng chạy", value=f"`Port: {session_data['port']}`", inline=True)
            
            # Format định dạng thời gian hết hạn sang chuỗi đọc được từ trường dữ liệu datetime
            if "expire_at" in session_data:
                expire_str = session_data["expire_at"].strftime("%H:%M:%S - %d/%m/%Y")
                embed.add_field(name="⏳ Hạn sử dụng", value=f"`{expire_str} (Trong 24h)`", inline=True)
            
            embed.set_footer(text="Mật khẩu này sẽ tự động thay đổi ngẫu nhiên mỗi khi bạn tạo phiên mới trên Web.")

            # Gửi tin nhắn ẩn danh, không sợ bị lộ trong kênh chat công cộng
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(TerminalCommand(bot))