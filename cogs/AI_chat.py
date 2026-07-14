import discord
from discord.ext import commands
from discord import app_commands
import httpx
import os
from collections import defaultdict

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = os.getenv("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.memory = defaultdict(list)
        
    @app_commands.command(name="ai", description="Trò chuyện lầy lội với AI Groq (Có thể tag người khác để joke)")
    @app_commands.describe(
        prompt="Nội dung bạn muốn nói/hỏi AI",
        user="Chọn người bạn muốn tag vào câu chuyện để AI 'cà khịa' cùng (Không bắt buộc)"
    )
    async def ai_chat(self, interaction: discord.Interaction, prompt: str, user: discord.User = None):
        if not self.api_key:
            await interaction.response.send_message(
                "❌ Backend chưa cấu hình `GROQ_API_KEY` trong file `.env` ní ơi!", 
                ephemeral=True
            )
            return

        await interaction.response.defer(thinking=True)
        user_id = interaction.user.id
        
        # Làm sạch hoặc khởi tạo hệ thống prompt chuyên về Dark Humour, Gen Z và Cà khịa
        if not self.memory[user_id]:
            self.memory[user_id].append({
                "role": "system", 
                "content": (
                    "Bạn là một trợ lý AI Gen Z, chúa hề, có khiếu hài hước (humour, joke, đôi khi là dark humour nhưng vô hại). "
                    "Nhiệm vụ của bạn là hùa theo các trò đùa của người dùng, biết tung hứng và cà khịa cực mạnh, không giảng đạo đức. "
                    "Đặc biệt: Nếu người dùng có nhắc tới hoặc tag một người khác trong ngữ cảnh (bằng định dạng <@ID>), "
                    "hãy nhắm vào người đó để đùa cợt, trêu ghẹo hoặc gán ghép hài hước theo đúng ý người dùng. "
                    "Ví dụ: Nếu hỏi 'thằng này có gay không', hãy hùa theo kiểu 'Nhìn cái cách <@ID> vuốt tóc là thấy uyển chuyển rồi đó' "
                    "hoặc '<@ID> nhìn men lỳ vậy thôi chứ bên trong là một hệ tư tưởng công chúa bong bóng'. "
                    "Xưng hô thân thiện bằng từ: ní, ông, tui, bro, fen. Trả lời ngắn gọn, mặn mòi, bắt trend."
                )
            })
            
        # Nếu Minh Triết có chọn một user để tag, mình lồng chuỗi mention vào prompt gửi cho AI hiểu luôn
        full_prompt = prompt
        if user:
            # Gửi kèm chuỗi định dạng <@ID> và Tên hiển thị để AI biết đường xử lý
            full_prompt = f"(Ngữ cảnh: Trong câu hỏi này có nhắc đến người tên là {user.display_name} có ID là <@{user.id}>). Nội dung: {prompt}"
        
        self.memory[user_id].append({"role": "user", "content": full_prompt})
        
        # Giới hạn bộ nhớ tránh quá tải token
        if len(self.memory[user_id]) > 7:
            self.memory[user_id] = [self.memory[user_id][0]] + self.memory[user_id][-6:]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": self.memory[user_id],
            "temperature": 0.85, # Tăng nhẹ độ sáng tạo cho AI bay bổng, hài hước hơn
            "max_tokens": 2048
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    ai_response = data["choices"][0]["message"]["content"]
                    
                    self.memory[user_id].append({"role": "assistant", "content": ai_response})
                    
                    if len(ai_response) > 1950:
                        ai_response = ai_response[:1950] + "\n..."
                    
                    # Trả tin nhắn text thuần thay vì Embed để tính năng MENTION PING hoạt động (Embed sẽ không kêu hoặc không sáng màu tag)
                    # Gửi kèm tên người hỏi lên đầu cho chuyên nghiệp
                    mention_prefix = f"💬 **{interaction.user.display_name} hỏi:** *{prompt}*\n\n"
                    await interaction.followup.send(f"{mention_prefix}{ai_response}")
                else:
                    await interaction.followup.send(f"❌ Lỗi API Groq: Mã {response.status_code}")
                    
        except httpx.TimeoutException:
            await interaction.followup.send("⏳ Groq phản hồi lâu quá ní ơi, thử lại phát nữa xem!")
        except Exception as e:
            await interaction.followup.send(f"❌ Lỗi hệ thống: `{str(e)}`")

    @app_commands.command(name="ai_clear", description="Xóa lịch sử trò chuyện với AI")
    async def ai_clear(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id in self.memory:
            del self.memory[user_id]
        await interaction.response.send_message("🧹 Đã làm mới bộ não của AI thành công!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AIChat(bot))
