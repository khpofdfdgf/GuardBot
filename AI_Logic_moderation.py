import json
import re
import aiohttp


class AIModeration:

    def __init__(self, gemini_key=None, groq_key=None):
        self.gemini_key = gemini_key
        self.groq_key = groq_key

    # =========================
    # PUBLIC MAIN ROUTER
    # =========================
    async def moderation_check(self, content: str) -> dict:
        """
        MAIN ENTRY:
        - thử Gemini trước (thông minh hơn)
        - fail thì qua Groq (nhanh + rẻ)
        - fail nữa thì fallback rule-based
        """

        result = await self.gemini_check(content)
        if result:
            return result

        result = await self.groq_check(content)
        if result:
            return result

        return self.fallback_check(content)

    # =========================
    # GEMINI CHECK
    # =========================
    async def gemini_check(self, content: str):
        if not self.gemini_key:
            return None

        prompt = self._build_prompt(content)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as res:
                    data = await res.json()

            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return self._parse_json(text)

        except:
            return None

    # =========================
    # GROQ CHECK
    # =========================
    async def groq_check(self, content: str):
        if not self.groq_key:
            return None

        prompt = self._build_prompt(content)

        url = "https://api.groq.com/openai/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as res:
                    data = await res.json()

            text = data["choices"][0]["message"]["content"]
            return self._parse_json(text)

        except:
            return None

    # =========================
    # FALLBACK RULE ENGINE
    # =========================
    def fallback_check(self, content: str):
        lower = content.lower()

        toxic_words = ["ngu", "địt", "cút", "dm", "đmm"]
        spam_words = ["http", "discord.gg", "free", "click"]

        return {
            "toxic": any(w in lower for w in toxic_words),
            "spam": any(w in lower for w in spam_words),
            "sexual": False,
            "hate": "kill" in lower,
            "scam": "free money" in lower,
            "reason": "fallback rule-based",
            "action": "warn"
        }

    # =========================
    # PROMPT BUILDER
    # =========================
    def _build_prompt(self, content: str):
        return f"""
You are a Discord moderation AI.

Analyze message:
"{content}"

Return ONLY JSON:
{{
  "toxic": true/false,
  "spam": true/false,
  "sexual": true/false,
  "hate": true/false,
  "scam": true/false,
  "reason": "short reason",
  "action": "allow/warn/mute/ban"
}}
"""

    # =========================
    # JSON PARSER SAFE
    # =========================
    def _parse_json(self, text: str):
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except:
            pass
        return None