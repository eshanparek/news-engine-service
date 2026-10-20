import os
import re
import json
import time
import logging
import requests
from typing import Dict, Optional, List

logger = logging.getLogger("AIAnalyzer")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-3.5-flash-lite"
]

# Comprehensive Financial Lexicon for High-Accuracy Rule-Based Scoring & Sector Mapping
BULLISH_KEYWORDS = [
    "SURGE", "RALLY", "SOARS", "JUMP", "GAIN", "CLIMBS", "HIGHEST", "EXPANDS", "RECORD HIGH",
    "BEATS ESTIMATES", "PROFIT RISES", "PROFIT JUMPS", "DIVIDEND", "BONUS", "BUYBACK",
    "ORDER WIN", "ACQUISITION", "APPROVED", "RATE CUT", "STIMULUS", "UPGRADED", "INVESTMENT",
    "EXEMPT", "TAX CUT", "GROWTH SURGES", "REBOUND", "BULL RUN", "PARTNERSHIP"
]

BEARISH_KEYWORDS = [
    "CRASH", "PLUNGE", "SLUMP", "TUMBLES", "EXTEND SLIDE", "FALLS", "SINKS", "DOWN", "PRESSURE",
    "LOSS WIDENS", "MISSES ESTIMATES", "RATE HIKE", "INFLATION SPIKES", "TARIFF", "SANCTION",
    "WAR", "ESCALATION", "DISRUPTION", "INVESTIGATION", "PENALTY", "FINE", "FRAUD", "DEFAULT",
    "DOWNGRADED", "WARNING", "SELL-OFF", "CRACKDOWN", "BAN", "STRIKE"
]

HIGH_VOLATILITY_TERMS = [
    "WAR", "MIDDLE EAST", "EMERGENCY", "CRASH", "SURGE", "RATE HIKE", "RATE CUT",
    "CRUDE OIL", "BRENT", "OPEC", "RBI", "FED", "CPI", "INFLATION", "TARIFF", "GDP", "US TREASURY"
]

SECTOR_MAP = {
    "BANKING": ["BANK", "RBI", "REPO", "NPA", "HDFC", "ICICI", "SBI", "KOTAK", "AXIS", "LOAN", "CREDIT", "NBFC", "FINANCE"],
    "ENERGY / OIL": ["CRUDE", "OIL", "BRENT", "GAS", "PETROL", "DIESEL", "OPEC", "ONGC", "RELIANCE", "IOC", "BPCL", "ENERGY"],
    "IT / TECH": ["IT", "TECH", "AI", "INFOSYS", "TCS", "WIPRO", "HCL", "TECH MAHINDRA", "SOFTWARE", "SAAS", "CHIP", "SEMICONDUCTOR"],
    "AUTO": ["AUTO", "CAR", "VEHICLE", "EV", "TATA MOTORS", "MARUTI", "MAHINDRA", "BAJAJ", "HERO", "COMPONENTS"],
    "METALS & COMMODITY": ["GOLD", "SILVER", "STEEL", "COPPER", "ALUMINIUM", "TATA STEEL", "JSW", "MINING", "COMMODITY"],
    "PHARMA": ["PHARMA", "DRUG", "FDA", "HEALTHCARE", "SUN PHARMA", "CIPLA", "REDDY", "MEDICINE", "HOSPITAL"],
    "REALTY & INFRA": ["REAL ESTATE", "HOUSING", "INFRA", "HIGHWAY", "L&T", "CONSTRUCTION", "CEMENT"]
}

class AIImpactAnalyzer:
    """
    Hybrid Market Sentiment & Impact Analyzer:
    Uses Google Gemini 2.5 when available, with an instant rule-based quantitative engine
    that guarantees 100% uptime with no blank fields or rate-limit failures.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.last_api_call = 0
        self.rate_limited_until = 0

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def heuristic_circular_analysis(self, title: str, text: str, regulator: str) -> Dict:
        """Fast rule-based institutional breakdown for official circulars & regulatory notices."""
        combined = f"{title} {text}".upper()
        
        # Determine category & impact
        if any(w in combined for w in ["MARGIN", "CIRCUIT", "SURVEILLANCE", "BAN", "PENALTY", "DEFAULT", "EXPIRE", "RESTRICTION", "DE-LISTING", "DELIST"]):
            impact = "HIGH"
            category = "Risk, Margins & Trading Rules"
        elif any(w in combined for w in ["REPO", "POLICY", "INTEREST RATE", "INFLATION", "LIQUIDITY", "CASH RESERVE", "CRR", "SLR"]):
            impact = "HIGH"
            category = "Monetary & Macro Policy"
        elif any(w in combined for w in ["TAX", "BUDGET", "CUSTOMS", "REVENUE", "FINANCE BILL", "EXEMPTION"]):
            impact = "HIGH"
            category = "Fiscal & Tax Regulation"
        elif any(w in combined for w in ["SETTLEMENT", "CLEARING", "HOLIDAY", "TIMING", "MOCK", "TESTING"]):
            impact = "MEDIUM"
            category = "Settlement & Market Operations"
        else:
            impact = "MEDIUM"
            category = "Compliance & Exchange Disclosure"

        bullets = [
            f"Official regulatory communication released by {regulator.upper()}.",
            f"Subject focus: {title.strip()[:110]}.",
            f"Operational Scope: Pertains to {category} across market participants."
        ]
        if "MARGIN" in combined:
            bullets.append("Traders & brokers must check revised margin requirements and exposure thresholds.")
        elif "SETTLEMENT" in combined or "HOLIDAY" in combined:
            bullets.append("Clearing corporations and depository participants to follow modified settlement schedules.")
        elif "REPO" in combined or "RATE" in combined:
            bullets.append("Direct macro implications for sovereign yields, banking liquidity, and lending rates.")
        else:
            bullets.append("Market intermediaries should review official documentation for procedural compliance.")

        return {
            "impact": impact,
            "category": category,
            "bullets": bullets[:5],
            "action_takeaway": f"Review {regulator.upper()} notification for compliance and operational readiness."
        }

    def analyze_circular(self, title: str, text: str, regulator: str) -> Dict:
        """
        Generate 3-5 bullet executive impact summary for regulatory circulars with direct native PDF links.
        Uses Gemini 2.5 with immediate heuristic fallback.
        """
        heuristic_res = self.heuristic_circular_analysis(title, text, regulator)

        if not self.is_configured() or time.time() < self.rate_limited_until:
            return heuristic_res

        prompt = f"""
You are a senior regulatory analyst for institutional trading. Analyze this official notification released by {regulator.upper()}:
Title: {title}
Content / Excerpt: {text[:2000]}

Generate an institutional executive summary.
Output ONLY a JSON object:
{{
  "impact": "HIGH" | "MEDIUM" | "LOW",
  "category": "<Trading Rules | Margins/Risk | Monetary Policy | Fiscal/Tax | Operations | Compliance>",
  "bullets": [
    "<Bullet 1: Exactly what regulation, rule, or policy was updated/introduced>",
    "<Bullet 2: Impact on brokers, institutions, or retail market participants>",
    "<Bullet 3: Deadlines, effective dates, or compliance requirements>",
    "<Bullet 4: Affected asset classes, sectors, or market contracts (e.g. F&O, Equity, FX, Crypto)>",
    "<Bullet 5: Actionable takeaway or key risk alert>"
  ],
  "action_takeaway": "<1-sentence direct actionable conclusion>"
}}
"""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        time_since_last = time.time() - self.last_api_call
        if time_since_last < 1.0:
            time.sleep(1.0 - time_since_last)

        for model in GEMINI_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            try:
                self.last_api_call = time.time()
                resp = requests.post(url, json=payload, timeout=7)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            raw_text = parts[0]["text"].strip()
                            if raw_text.startswith("```json"):
                                raw_text = raw_text[7:-3].strip()
                            elif raw_text.startswith("```"):
                                raw_text = raw_text[3:-3].strip()

                            start = raw_text.find("{")
                            end = raw_text.rfind("}") + 1
                            parsed = json.loads(raw_text[start:end]) if start >= 0 and end > start else json.loads(raw_text)

                            imp = str(parsed.get("impact", "MEDIUM")).upper()
                            if imp not in ("HIGH", "MEDIUM", "LOW"):
                                imp = heuristic_res["impact"]
                            
                            bullets = parsed.get("bullets", [])
                            if not isinstance(bullets, list) or len(bullets) < 2:
                                bullets = heuristic_res["bullets"]
                            else:
                                bullets = [str(b).strip() for b in bullets[:5] if str(b).strip()]

                            return {
                                "impact": imp,
                                "category": str(parsed.get("category", heuristic_res["category"])),
                                "bullets": bullets,
                                "action_takeaway": str(parsed.get("action_takeaway", heuristic_res["action_takeaway"]))
                            }
                elif resp.status_code == 429:
                    self.rate_limited_until = time.time() + 60
                    break
            except Exception as e:
                logger.debug(f"Gemini circular analysis error on {model}: {e}")

        return heuristic_res

    def heuristic_analysis(self, title: str, summary: str) -> Dict:
        """Fast rule-based financial sentiment & impact analyzer."""
        text = f"{title} {summary}".upper()
        
        # 1. Determine Sentiment
        bull_score = sum(2 for w in BULLISH_KEYWORDS if w in text)
        bear_score = sum(2 for w in BEARISH_KEYWORDS if w in text)

        if bull_score > bear_score:
            sentiment = "BULLISH"
        elif bear_score > bull_score:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"

        # 2. Determine Impact Score (1-10)
        base_score = 5
        volatility_matches = sum(1 for w in HIGH_VOLATILITY_TERMS if w in text)
        base_score += min(volatility_matches * 2, 4)
        if bull_score > 3 or bear_score > 3:
            base_score += 1
        
        score = min(max(base_score, 1), 10)
        impact = "HIGH" if score >= 8 else ("MEDIUM" if score >= 5 else "LOW")

        # 3. Detect Affected Sectors
        detected_sectors = []
        for sector, keywords in SECTOR_MAP.items():
            if any(kw in text for kw in keywords):
                detected_sectors.append(sector)
        if not detected_sectors:
            detected_sectors = ["Broad Market / Macro"]

        # 4. Generate Concise Market Context
        if sentiment == "BULLISH":
            reasoning = f"Positive development in {detected_sectors[0]}; expected to support market sentiment."
        elif sentiment == "BEARISH":
            reasoning = f"Elevated headwinds in {detected_sectors[0]}; likely to induce volatility or selling pressure."
        else:
            reasoning = f"Standard market development affecting {detected_sectors[0]} with neutral short-term bias."

        return {
            "score": score,
            "sentiment": sentiment,
            "impact": impact,
            "sectors": detected_sectors,
            "reasoning": reasoning
        }

    def analyze_news(self, title: str, summary: str, source: str = "") -> Dict:
        """Analyze news item using Gemini LLM with instant heuristic fallback."""
        # Always compute baseline
        heuristic_res = self.heuristic_analysis(title, summary)

        if not self.is_configured() or time.time() < self.rate_limited_until:
            return heuristic_res

        prompt = f"""
Analyze this financial headline and summary for its immediate impact on Indian & Global Markets:

Headline: {title}
Summary: {summary}
Source: {source}

Output ONLY a JSON object:
{{
  "score": <1-10 integer>,
  "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
  "impact": "HIGH" | "MEDIUM" | "LOW",
  "sectors": ["<SECTOR OR STOCK>"],
  "reasoning": "<concise 1-sentence market rationale>"
}}
"""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }

        # Cooldown spacing
        time_since_last = time.time() - self.last_api_call
        if time_since_last < 1.0:
            time.sleep(1.0 - time_since_last)

        for model in GEMINI_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            try:
                self.last_api_call = time.time()
                resp = requests.post(url, json=payload, timeout=6)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            text = parts[0]["text"].strip()
                            if text.startswith("```json"):
                                text = text[7:-3].strip()
                            elif text.startswith("```"):
                                text = text[3:-3].strip()

                            start = text.find("{")
                            end = text.rfind("}") + 1
                            parsed = json.loads(text[start:end]) if start >= 0 and end > start else json.loads(text)

                            sent = str(parsed.get("sentiment", parsed.get("impact", "NEUTRAL"))).upper()
                            if "POS" in sent: sent = "BULLISH"
                            elif "NEG" in sent: sent = "BEARISH"
                            elif sent not in ("BULLISH", "BEARISH", "NEUTRAL"): sent = heuristic_res["sentiment"]

                            sc = int(parsed.get("score", heuristic_res["score"]))
                            imp = str(parsed.get("impact", "MEDIUM")).upper()
                            if imp not in ("HIGH", "MEDIUM", "LOW"):
                                imp = "HIGH" if sc >= 8 else ("MEDIUM" if sc >= 5 else "LOW")

                            sec = parsed.get("sectors") or heuristic_res["sectors"]
                            rs = str(parsed.get("reasoning") or heuristic_res["reasoning"])

                            return {
                                "score": sc,
                                "sentiment": sent,
                                "impact": imp,
                                "sectors": sec,
                                "reasoning": rs
                            }
                elif resp.status_code == 429:
                    logger.warning(f"Gemini API rate limit reached on {model}, cooling down.")
                    self.rate_limited_until = time.time() + 60 # 60s cooldown
                    break
            except Exception as e:
                logger.debug(f"Gemini error on {model}: {e}")

        # Fallback to heuristic result if API is cooling down or rate limited
        return heuristic_res

# Global instance
ai_analyzer = AIImpactAnalyzer()
