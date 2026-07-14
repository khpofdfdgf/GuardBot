"""
cogs/guardbot.py
Group chính của GuardBot với Live Web Terminal qua Cloudflare Tunnel
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import time
import psutil
import platform
import os
import subprocess
import random
import re

# Cấu hình ID của các Owner được quyền sử dụng Terminal
OWNER_IDS = [
    1269843192883314710,
    971364191892045844,
    1210954954483699794,
    911471561758875678
]

class StatusView(discord.ui.View):
    def __init__(self, cog: GuardBot):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Cập nhật", style=discord.ButtonStyle.green, emoji="🔄", custom_id="btn_refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = self.cog.create_status_embed()
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Kiểm tra Dịch vụ", style=discord.ButtonStyle.blurple, emoji="🖥️", custom_id="btn_services")
    async def check_services(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        services = ["ssh", "nginx", "mysql", "docker", "cloudflared"]
        status_results = []

        for service in services:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service], 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    text=True, 
                    timeout=2
                )
                status = result.stdout.strip()
                if status == "active":
                    status_results.append(f"🟢 **{service.upper()}**: `Đang chạy (Active)`")
                else:
                    status_results.append(f"🔴 **{service.upper()}**: `Đã dừng ({status})`")
            except Exception:
                status_results.append(f"⚪ **{service.upper()}**: `Không tìm thấy / Lỗi`")

        service_embed = discord.Embed(title="🛠️ Ubuntu Services Status", description="\n".join(status_results), color=0x5865F2)
        await interaction.followup.send(embed=service_embed, ephemeral=True)

    # NÚT MỞ TERMINAL QUA CLOUDFLARE
    @discord.ui.button(label="Mở Terminal", style=discord.ButtonStyle.gray, emoji="💻", custom_id="btn_terminal")
    async def open_terminal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in OWNER_IDS:
            await interaction.response.send_message("❌ Bạn không có quyền truy cập Terminal của Server này!", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)

        # 1. Tạo Port và Mật mã ngẫu nhiên cho ttyd
        port = random.randint(5000, 6000)
        secret_pass = f"guard_{random.randint(100000, 999999)}"

        # Khởi động ttyd chạy ngầm trên localhost
        ttyd_cmd = f"ttyd -p {port} -c admin:{secret_pass} tmux attach -t guardbot || tmux new -s guardbot &"
        subprocess.Popen(ttyd_cmd, shell=True)
        time.sleep(1)

        # 2. Khởi động Cloudflare Quick Tunnel trỏ vào port vừa tạo và ghi log ra file tạm
        log_file = f"/tmp/cf_tunnel_{port}.log"
        cf_cmd = f"cloudflared tunnel --url http://localhost:{port} > {log_file} 2>&1 &"
        subprocess.Popen(cf_cmd, shell=True)
        
        # Đợi 3 giây để Cloudflare thiết lập đường ống và lấy link liên kết
        time.sleep(3)

        # Đọc file log để tìm đường link dạng https://*.trycloudflare.com
        tunnel_url = "Không thể khởi tạo link Cloudflare"
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                log_content = f.read()
                # Tìm đoạn link trycloudflare bằng Regex
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", log_content)
                if match:
                    tunnel_url = match.group(0)
            
            # Xóa file log tạm sau khi lấy xong link để sạch sẽ hệ thống
            try: os.remove(log_file)
            except: pass

        if "trycloudflare.com" not in tunnel_url:
            await interaction.followup.send("❌ **Lỗi:** Không thể kết nối tới Cloudflare Tunnel. Hãy chắc chắn VPS đã cài `cloudflared`.", ephemeral=True)
            return

        # 3. Gửi Embed chứa link Cloudflare bảo mật HTTPS
        embed = discord.Embed(
            title="☁️ Cloudflare Secured Terminal",
            description=(
                f"Đường ống bảo mật Cloudflare Tunnel đã được thiết lập thành công!\n"
                f"🔒 *IP gốc của VPS hoàn toàn ẩn danh, kết nối được mã hóa HTTPS.*\n\n"
                f"🌐 **Đường dẫn Terminal:** [Bấm vào đây để mở]({tunnel_url})\n"
                f"👤 **Tài khoản:** `admin`\n"
                f"🔑 **Mật khẩu:** `{secret_pass}`\n\n"
                f"⚠️ *Lưu ý: Bạn có thể cấu hình bao lâu tùy thích. Khi tắt tab trình duyệt, phiên làm việc sẽ tự đóng.*"
            ),
            color=0xF38020 # Màu cam đặc trưng của Cloudflare
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


class GuardBot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    def create_status_embed(self) -> discord.Embed:
        def make_bar(percent: float) -> str:
            sliced = int(percent / 10)
            return "█" * sliced + "░" * (10 - sliced)

        latency = round(self.bot.latency * 1000)
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        total_guilds = len(self.bot.guilds)
        total_users = sum(guild.member_count for guild in self.bot.guilds if guild.member_count)

        process = psutil.Process(os.getpid())
        bot_ram_usage = round(process.memory_info().rss / (1024 ** 2), 1)

        cpu_usage = psutil.cpu_percent(interval=None)
        cpu_emoji = "🚨" if cpu_usage > 85 else "⚙️"

        ram = psutil.virtual_memory()
        ram_used = round(ram.used / (1024 ** 3), 2)
        ram_total = round(ram.total / (1024 ** 3), 2)
        ram_emoji = "🚨" if ram.percent > 85 else "🧠"

        disk = psutil.disk_usage('/')
        disk_used = round(disk.used / (1024 ** 3), 2)
        disk_total = round(disk.total / (1024 ** 3), 2)
        disk_emoji = "🚨" if disk.percent > 90 else "💽"

        net_io = psutil.net_io_counters()
        net_sent = round(net_io.bytes_sent / (1024 ** 2), 1)
        net_recv = round(net_io.bytes_recv / (1024 ** 2), 1)

        embed_color = 0xED4245 if (cpu_usage > 85 or ram.percent > 85) else 0x43B581

        embed = discord.Embed(title="🛡️ GuardBot System Dashboard", color=embed_color)
        embed.add_field(name="🤖 GuardBot Info", value=f"⚡ **Ping:** `{latency}ms`\n⏱️ **Uptime:** `{uptime_str}`\n🌐 **Servers:** `{total_guilds}`\n👥 **Users:** `{total_users}`\n📟 **Bot RAM:** `{bot_ram_usage} MB`", inline=True)
        embed.add_field(name="💻 Environment", value=f"🐍 **Python:** `v{platform.python_version()}`\n📦 **Library:** `d.py v{discord.__version__}`\n🖥️ **OS:** `Ubuntu Linux`\n🧵 **Threads:** `{process.num_threads()}`", inline=True)
        embed.add_field(name="📊 Server Hardware Status", value=f"{cpu_emoji} **CPU Usage:** `{cpu_usage}%`\n`[{make_bar(cpu_usage)}]`\n\n{ram_emoji} **RAM Usage:** `{ram_used}GB` / `{ram_total}GB` (`{ram.percent}%`)\n`[{make_bar(ram.percent)}]`\n\n{disk_emoji} **Disk Space:** `{disk_used}GB` / `{disk_total}GB` (`{disk.percent}%`)\n`[{make_bar(disk.percent)}]`\n\n" f"📡 **Network Traffic:** 📤 `{net_sent}MB` | 📥 `{net_recv}MB`", inline=False)
        
        current_time = time.strftime("%H:%M:%S", time.localtime())
        embed.set_footer(text=f"GuardBot Security • Cập nhật lúc: {current_time}")
        return embed

    guardbot = app_commands.Group(name="guardbot", description="GuardBot Security System")

    @guardbot.command(name="info", description="Thông tin GuardBot")
    async def info(self, interaction: discord.Interaction):
        guild = interaction.guild
        humans = len([m for m in guild.members if not m.bot])
        bots = len([m for m in guild.members if m.bot])
        embed = discord.Embed(title="🛡️ GuardBot Security Center", description="Hệ thống quản lý và kiểm duyệt server.\n\n• Moderation\n• Appeals\n• Staff Proposals\n• Case Logging\n• Statistics", color=0x2F3136)
        embed.add_field(name="📊 Thống kê", value=f"👥 Người dùng: **{humans}**\n🤖 Bot: **{bots}**\n🎭 Role: **{len(guild.roles)}**", inline=False)
        embed.set_footer(text="GuardBot v3.0")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="status", description="Kiểm tra trạng thái hoạt động và tài nguyên phần cứng của Bot")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = self.create_status_embed()
        view = StatusView(self)
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(GuardBot(bot))