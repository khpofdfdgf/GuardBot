import asyncio
import uvicorn
from discord.ext import commands

from web.main import app as web_app
from web.websockets import manager
from config import cfg

class WebDashboard(commands.Cog):
    """Cog để chạy Web Dashboard bằng FastAPI/Uvicorn trong loop của bot."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.task = None

    async def cog_load(self):
        # Inject bot instance into web app
        web_app.state.bot = self.bot
        # Start uvicorn server as a background task
        self.task = self.bot.loop.create_task(self.run_fastapi())
        print(f"✅ Web Dashboard starting on port {cfg.web_port}...")

    async def cog_unload(self):
        if self.task and not self.task.done():
            self.task.cancel()
            print("🛑 Web Dashboard stopped.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild:
            data = {
                "event": "message",
                "id": str(message.id),
                "author": str(message.author),
                "author_avatar": message.author.display_avatar.url if message.author.display_avatar else None,
                "content": message.content,
                "channel_id": str(message.channel.id),
                "channel_name": str(message.channel.name),
                "guild_id": str(message.guild.id)
            }
            self.bot.loop.create_task(manager.broadcast_json(data))

    async def run_fastapi(self):
        config = uvicorn.Config(web_app, host="0.0.0.0", port=cfg.web_port, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()

async def setup(bot: commands.Bot):
    await bot.add_cog(WebDashboard(bot))
