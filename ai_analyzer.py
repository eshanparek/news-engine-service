import os
import json
import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger("AIAnalyzer")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

class AIImpactAnalyzer:
    """
    Evaluates news headlines & summaries for market sentiment and impact score (1-10)
    using Google Gemini API.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def analyze_news(self, title: str, summary: str, source: str = "") -> Dict:
        """
        Rate market impact, direction, and reasoning for a news article.
        Returns: {
            "score": 1-10,
            "impact": "POSITIVE" | "NEGATIVE" | "NEUTRAL",
            "sectors": ["BANKING", "IT", ...],
            "reasoning": "..."
        }
        """
        if not self.is_configured():
            return {
                "score": 5,
                "impact": "NEUTRAL",
                "sectors": [],
                "reasoning": "AI analysis not configured (GEMINI_API_KEY missing)"
            }

        prompt = f"""
Analyze the following financial/market news item for its expected immediate impact on the Indian Stock Market (NSE/BSE) and global markets:

Title: {title}
Summary: {summary}
Source: {source}

Respond with ONLY a valid JSON object in this exact schema:
{{
  "score": <integer from 1 to 10 where 1 is trivial and 10 is high volatility catalyst>,
  "impact": "POSITIVE" | "NEGATIVE" | "NEUTRAL",
  "sectors": ["<affected sector or stock ticker>", "..."],
  "reasoning": "<concise 1-sentence explanation of market impact>"
}}
"""

        # Try gemini-1.5-flash endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 200,
                "responseMimeType": "application/json"
            }
        }

        try:
            resp = requests.post(url, json=payload, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                
                # Strip markdown fence if present
                if text.startswith("```json"):
                    text = text[7:-3].strip()
                elif text.startswith("```"):
                    text = text[3:-3].strip()

                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    parsed = json.loads(text[start:end])
                else:
                    parsed = json.loads(text)

                return {
                    "score": int(parsed.get("score", 5)),
                    "impact": str(parsed.get("impact", "NEUTRAL")).upper(),
                    "sectors": parsed.get("sectors", []),
                    "reasoning": str(parsed.get("reasoning", ""))
                }
            else:
                logger.warning(f"Gemini API returned status {resp.status_code}: {resp.text[:120]}")
        except Exception as e:
            logger.error(f"Error during AI analysis: {e}")

        return {
            "score": 5,
            "impact": "NEUTRAL",
            "sectors": [],
            "reasoning": "AI analysis unavailable"
        }

# Global instance
ai_analyzer = AIImpactAnalyzer()
