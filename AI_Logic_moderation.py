import os
import re
import json
import requests

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

URL = "https://api.groq.com/openai/v1/chat/completions"


def groq_check(message: str) -> dict:
    try:

        payload = {
            "model": "llama-3.3-70b-versatile",
            "temperature": 0,
            "max_tokens": 50,
            "response_format": {
                "type": "json_object"
            },
            "messages": [
              {
    "role": "system",
    "content": """
You are a Discord moderation classifier.

Return ONLY valid JSON.

Your task is to detect ONLY content that clearly violates server rules.

LABELS:
SAFE
HARASSMENT
HATE
POLITICS
AD
SPAM

SAFE:
- Casual conversation
- Gaming chat
- Technical discussions
- Programming code
- Questions
- News discussion
- Friendly teasing
- Memes
- Reactions
- Emojis
- Stickers
- GIFs
- Short messages
- Mentions

HARASSMENT:
- Direct insults toward a person
- Personal attacks
- Bullying
- Threats
- Targeted abuse

Examples HARASSMENT:
- "mày ngu vl"
- "thằng chó"
- "con đĩ"
- "óc chó"
- "cút mẹ đi"
- "tao ghét mày"

NOT HARASSMENT:
- Generic profanity
- Swearing without a target
- Expressions of frustration

Examples SAFE:
- "địt mẹ lag quá"
- "vcl game này khó"
- "cc gì vậy"
- "má nó cay"

HATE:
- Racism
- Religious hostility
- Ethnic hostility
- Hate speech
- Calls for discrimination

POLITICS:
- Political propaganda
- Political extremism
- Political attacks
- Calls for political violence

AD:
- Selling products
- Recruitment
- Advertisements
- Scams
- Crypto promotion
- Investment promotion

SPAM:
- Flooding
- Repeated messages
- Mass mentions
- Mass emoji spam

IMPORTANT:

Single profanity alone is usually SAFE.

Only classify HARASSMENT when a person is being targeted.

If uncertain -> SAFE.

Return JSON only:

{
    "label":"SAFE|HARASSMENT|HATE|POLITICS|AD|SPAM",
    "score":0.00
}
"""
},

                
                {
                    "role": "user",
                    "content": message
                }
            ]
        }

        r = requests.post(
            URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=15
        )

        r.raise_for_status()

        data = r.json()

        content = (
            data["choices"][0]
            ["message"]
            ["content"]
            .strip()
        )

        # remove markdown fences
        content = re.sub(
            r"^```json|```$",
            "",
            content,
            flags=re.MULTILINE
        ).strip()
        print("\n===== GROQ RAW =====")
        print(content)
        print("====================\n")
        result = json.loads(content)

        label = str(
            result.get("label", "SAFE")
        ).upper()

        score = float(
            result.get("score", 0)
        )

        return {
            "label": label,
            "score": max(
                0,
                min(score, 1)
            )
        }

    except Exception as e:
        print("[GROQ ERROR]", repr(e))

        return {
            "label": "SAFE",
            "score": 0
        }