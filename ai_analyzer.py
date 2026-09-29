import os
import json
import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger("AIAnalyzer")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Supported models on modern API: gemini-2.5-flash, gemini-flash-latest, gemini-2.5-flash-lite
GEMINI_MODELS = [
    os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash"
]

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
        Rate market impact, sentiment, and reasoning for a news article.
        Returns: {
            "score": 1-10,
            "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
            "impact": "HIGH" | "MEDIUM" | "LOW",
            "sectors": ["BANKING", "IT", ...],
            "reasoning": "..."
        }
        """
        if not self.is_configured():
            return {
                "score": 5,
                "sentiment": "NEUTRAL",
                "impact": "LOW",
                "sectors": [],
                "reasoning": "AI analysis not configured (GEMINI_API_KEY missing)"
            }

        prompt = f"""
Analyze the following financial/market news item for its expected immediate impact and sentiment on the Indian Stock Market (NSE/BSE) and global markets:

Headline: {title}
Summary: {summary}
Source: {source}

Respond with ONLY a valid JSON object in this exact schema:
{{
  "score": <integer from 1 to 10 where 1 is minimal and 10 is massive volatility catalyst>,
  "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
  "impact": "HIGH" | "MEDIUM" | "LOW",
  "sectors": ["<affected sector or stock ticker>", "..."],
  "reasoning": "<concise 1-sentence explanation of market sentiment and effect>"
}}
"""

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 200,
                "responseMimeType": "application/json"
            }
        }

        for model in GEMINI_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            try:
                resp = requests.post(url, json=payload, timeout=6)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text = candidates[0]["content"]["parts"][0]["text"].strip()
                        
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

                        sentiment = str(parsed.get("sentiment", parsed.get("impact", "NEUTRAL"))).upper()
                        if "POS" in sentiment: sentiment = "BULLISH"
                        elif "NEG" in sentiment: sentiment = "BEARISH"
                        elif sentiment not in ("BULLISH", "BEARISH", "NEUTRAL"): sentiment = "NEUTRAL"

                        impact_level = str(parsed.get("impact", "MEDIUM")).upper()
                        if impact_level not in ("HIGH", "MEDIUM", "LOW"):
                            score_val = int(parsed.get("score", 5))
                            impact_level = "HIGH" if score_val >= 8 else ("MEDIUM" if score_val >= 5 else "LOW")

                        return {
                            "score": int(parsed.get("score", 5)),
                            "sentiment": sentiment,
                            "impact": impact_level,
                            "sectors": parsed.get("sectors", []),
                            "reasoning": str(parsed.get("reasoning", ""))
                        }
                else:
                    logger.debug(f"Gemini model {model} returned status {resp.status_code}")
            except Exception as e:
                logger.debug(f"Error calling Gemini model {model}: {e}")

        return {
            "score": 5,
            "sentiment": "NEUTRAL",
            "impact": "LOW",
            "sectors": [],
            "reasoning": "AI analysis unavailable"
        }

# Global instance
ai_analyzer = AIImpactAnalyzer()
