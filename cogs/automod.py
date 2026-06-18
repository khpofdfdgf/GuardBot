from __future__ import annotations

import re
import requests
import os
from dotenv import load_dotenv
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
import json
import discord
from discord.ext import commands
from AI_Logic_moderation import groq_check
from config import cfg, COLOR_ERROR, COLOR_WARN
import utils

load_dotenv()

JAIL_ROLE_ID = 1414255151920844852
# =========================
# AI (Grok / xAI)
# =========================






# =========================
# Regex caches
# =========================
_PHONE_RE = re.compile(r"(?<!\d)(0[3-9]\d{8}|\+84[3-9]\d{8})(?!\d)")

_AD_CACHE = {"patterns": None, "regex": None}
_SUS_CACHE = {"domains": None, "regex": None}


def _get_ad_re():
    p = cfg.ad_patterns
    if _AD_CACHE["patterns"] == p:
        return _AD_CACHE["regex"]
    if not p:
        return None
    r = re.compile("|".join(p), re.IGNORECASE)
    _AD_CACHE.update({"patterns": list(p), "regex": r})
    return r


def _get_sus_re():
    d = cfg.suspicious_domains
    if _SUS_CACHE["domains"] == d:
        return _SUS_CACHE["regex"]
    if not d:
        return None
    r = re.compile("|".join(map(re.escape, d)), re.IGNORECASE)
    _SUS_CACHE.update({"domains": list(d), "regex": r})
    return r


# =========================
# AutoMod Cog
# =========================
class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.msg_cache = defaultdict(lambda: deque(maxlen=25))
        self.cooldown = defaultdict(float)

    # -------------------------
    async def log(self, guild, embed):
        ch = guild.get_channel(cfg.mod_log_channel_id)
        if ch:
            await ch.send(embed=embed)

    # -------------------------
    def is_spam(self, uid, content):
        now = datetime.now(timezone.utc).timestamp()
        cache = self.msg_cache[uid]

        cache.append((now, content))

        recent = [c for t, c in cache if now - t <= cfg.spam_window]
        return recent.count(content) >= cfg.spam_threshold

    # -------------------------
    def cooldown_hit(self, uid):
        now = datetime.now(timezone.utc).timestamp()
        if now - self.cooldown[uid] < 2:
            return True
        self.cooldown[uid] = now
        return False

    # -------------------------

    async def punish(self, message, reason_type, reason, auto_warn=True, evidence=None):
        member = message.author
        guild = message.guild

        print("\n" + "-" * 50)
        print(f"[PUNISH] {member} | {reason_type} | {reason}")

        # =========================
        # 1. DELETE MESSAGE
        # =========================
        try:
            await message.delete()
            print("[DELETE] Message deleted")
        except Exception as e:
            print("[DELETE ERROR]", e)

        total = 0

        # =========================
        # 2. WARN SYSTEM
        # =========================
        if auto_warn:
            total = utils.add_warning(
                member.id,
                self.bot.user.id,
                reason,
                guild.id
            )

            utils.log_case(
                "AUTO-WARN",
                member,
                self.bot.user,
                reason
            )

            wp = cfg.warn_punishments
            action, duration = wp.get(str(total), ["mutejail", 0])

            print(f"[WARN] Total warnings: {total}")
            print(f"[PUNISH RULE] {action} | {duration}")

            # =========================
            # 3. ACTION SYSTEM
            # =========================

            if action == "mutejail":
                role = guild.get_role(JAIL_ROLE_ID)

                if role:
                    try:
                        await member.add_roles(
                            role,
                            reason=reason
                        )
                        print("[MUTEJAIL] Role assigned")

                    except Exception as e:
                        print("[MUTEJAIL ERROR]", e)

                else:
                    print("[MUTEJAIL] Role not found")

            elif action == "ban":
                try:
                    await guild.ban(
                        member,
                        reason=reason
                    )
                    print("[BAN] User banned")

                except Exception as e:
                    print("[BAN ERROR]", e)

        # =========================
        # 4. DM USER
        # =========================
        try:
            await member.send(
                f"⚠️ Bạn bị xử lý: {reason_type}\n"
                f"Lý do: {reason}"
                f"📝 Nội dung vi phạm:\n"
                f"```{evidence or message.content}```"
            )
            print("[DM] Sent")

        except Exception as e:
            print("[DM ERROR]", e)

        # =========================
        # 5. LOG TO SERVER
        # =========================
        embed = discord.Embed(
            title=f"AutoMod: {reason_type}",
            description=f"{member.mention} → {reason}",
            color=0xFF0000
        )

        embed.add_field(
            name="🚫 Nội dung vi phạm",
            value=f"```{evidence or message.content}```"[:1024],
            inline=False
        )

        await self.log(guild, embed)
        print("[LOG] Sent to mod channel")


        # -------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
            if not message.guild or message.author.bot:
                return

            member = message.author
            content = message.content

            import re
            import unicodedata

            # =========================
            # NORMALIZE (QUAN TRỌNG)
            # =========================
            def normalize(text: str) -> str:
                text = text.lower()
                text = unicodedata.normalize("NFKC", text)
                text = re.sub(r"[^\w\s]", "", text)
                text = re.sub(r"\s+", " ", text).strip()
                return text

            lower = normalize(content)

            print("\n" + "=" * 60)
            print(f"[MSG] {member} | {member.id}")
            print(f"[RAW] {content}")
            print(f"[NORM] {lower}")

            # =========================
            # FAST FILTERS (spam/link/ad/pii)
            # =========================

            if self.is_spam(member.id, content):
                print("[SPAM]")
                return await self.punish(message, "SPAM", "Spam detected")

            if _PHONE_RE.search(content):
                print("[PII]")
                return await self.punish(message, "PII", "Phone detected")

            sus_re = _get_sus_re()
            if sus_re and sus_re.search(lower):
                print("[LINK]")
                return await self.punish(message, "LINK", "Suspicious link")

            ad_re = _get_ad_re()
            if ad_re and ad_re.search(lower):
                print("[AD]")
                return await self.punish(message, "AD", "Advertisement")

            if len(message.mentions) > cfg.max_mentions:
                return await self.punish(message, "MENTION", "Mention spam")

            # =========================
            # HATE PATTERN (anti né filter)
            # =========================

            HATE_PATTERNS = [
                r"(may|mày).*(ngu|khùng|chết|cút|điên)",
                r"(con cho|con lon|con rác)",
                r"(vcl|vl|cc|clm|dmm|dm)"
            ]

            risk = 0

            print("[CHECK] Hate patterns...")

            for p in HATE_PATTERNS:
                if re.search(p, lower):
                    print(f"[HATE PATTERN HIT] {p}")
                    risk += 0.5
                    break

            # =========================
            # KEYWORD LIST (LOW WEIGHT)
            # =========================

            for kw in cfg.hate_keywords:
                if kw in lower:
                    print(f"[KEYWORD HIT] {kw}")
                    risk += 0.3
                    break

            # =========================
            # AI HATE DETECTION (MAIN BRAIN)
            # =========================

            print("[AI] analyzing...")

            ai = groq_check(content)

            print(f"[AI RESULT] {ai}")

            label = ai.get("label", "SAFE")
            score = float(ai.get("score", 0))

            if label in ["HATE", "HARASSMENT"]:
                risk += score

            if label in ["SPAM", "AD", "POLITICS"] and score > 0.7:
                risk += score * 0.7

            # =========================
            # EMOJI / OTHER NOISE
            # =========================

            emoji_count = len(re.findall(r"<a?:\w+:\d+>|[\U0001F300-\U0001FAFF]", content))
            if emoji_count > cfg.max_emoji:
                risk += 0.2

            print(f"[RISK SCORE] {risk}")

            # =========================
            # DECISION ENGINE
            # =========================

            if risk >= 0.6:
                return await self.punish(
                    message,
                    "HATE",
                    f"risk={risk:.2f} | ai={label}:{score:.2f}",
                    evidence=content
                )

            print("[SAFE]")
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))