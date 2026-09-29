import os
import time
import logging
import requests
from typing import Dict

logger = logging.getLogger("TelegramNotifier")

class TelegramNotifier:
    """
    Sends structured breaking news alerts directly to Telegram channel / chat
    with distinct visual highlights for high-impact market catalysts.
    """
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.enabled = os.getenv("ENABLE_TELEGRAM_ALERTS", "true").lower() == "true"

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_news_alert(self, news: Dict) -> bool:
        if not self.enabled or not self.is_configured():
            return False

        ai_score = news.get("ai_score", 5)
        ai_sentiment = news.get("ai_sentiment", "NEUTRAL")
        ai_impact = news.get("ai_impact", "MEDIUM")
        ai_reasoning = news.get("ai_reasoning", "")
        ai_sectors = news.get("ai_sectors", [])
        relevance = news.get("relevance", 0)
        source = news.get("source", "Market Wire")
        title = news.get("title", "")
        link = news.get("link", "#")

        # Determine if High Priority (Score >= 8 or Impact == 'HIGH')
        is_high_impact = (ai_score >= 8) or (ai_impact == "HIGH") or (relevance >= 80)

        # Sentiment badge
        if ai_sentiment == "BULLISH":
            sentiment_label = "🟢 BULLISH"
        elif ai_sentiment == "BEARISH":
            sentiment_label = "🔴 BEARISH"
        else:
            sentiment_label = "⚪ NEUTRAL"

        sectors_str = ", ".join(ai_sectors) if ai_sectors else "Broad Market"

        if is_high_impact:
            header = (
                "🚨🚨🚨 <b>HIGH IMPACT MARKET CATALYST</b> 🚨🚨🚨\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            score_line = f"🔥 <b>AI Impact Score:</b> <b>{ai_score}/10 [HIGH VOLATILITY]</b>"
        else:
            header = (
                "📰 <b>MARKET NEWS UPDATE</b>\n"
                "──────────────────────"
            )
            score_line = f"🤖 <b>AI Impact Score:</b> {ai_score}/10"

        context_block = f"\n💡 <b>Analysis:</b> <i>{ai_reasoning}</i>" if ai_reasoning else ""

        text = (
            f"{header}\n\n"
            f"<b>{title}</b>\n\n"
            f"{score_line}\n"
            f"📊 <b>Sentiment:</b> {sentiment_label}\n"
            f"🎯 <b>Affected:</b> {sectors_str}"
            f"{context_block}\n\n"
            f"🏛 <b>Source:</b> {source} | <b>Relevance:</b> {relevance}%\n"
            f"🔗 <a href='{link}'>Read Full Article</a>"
        )

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }

        try:
            resp = requests.post(url, json=payload, timeout=6)
            if resp.status_code == 200:
                logger.info(f"[TG ALERT] Sent {'(HIGH IMPACT) ' if is_high_impact else ''}for: {title[:40]}...")
                return True
            else:
                logger.warning(f"Telegram API failed ({resp.status_code}): {resp.text[:120]}")
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")

        return False

# Global instance
telegram_notifier = TelegramNotifier()
