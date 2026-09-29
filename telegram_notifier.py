import os
import time
import logging
import requests
from typing import Dict

logger = logging.getLogger("TelegramNotifier")

class TelegramNotifier:
    """
    Sends structured breaking news alerts directly to Telegram channel / chat.
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

        ai_score = news.get("ai_score", 0)
        ai_impact = news.get("ai_impact", "NEUTRAL")
        ai_reasoning = news.get("ai_reasoning", "")
        relevance = news.get("relevance", 0)

        # Impact icon
        if ai_impact == "POSITIVE":
            impact_emoji = "🟢 POSITIVE"
        elif ai_impact == "NEGATIVE":
            impact_emoji = "🔴 NEGATIVE"
        else:
            impact_emoji = "⚪ NEUTRAL"

        ai_block = ""
        if ai_score > 0:
            ai_block = f"\n\n<b>AI Impact Score:</b> {ai_score}/10 | {impact_emoji}\n<b>Context:</b> <i>{ai_reasoning}</i>"

        text = (
            f"🚨 <b>BREAKING MARKET NEWS</b>\n\n"
            f"📰 <b>{news.get('title', 'News Update')}</b>\n\n"
            f"<b>Source:</b> {news.get('source', 'Financial Wire')}\n"
            f"<b>Relevance:</b> {relevance}%"
            f"{ai_block}\n\n"
            f"🔗 <a href='{news.get('link', '#')}'>Read Original Story</a>"
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
                logger.info(f"Sent Telegram alert for: {news.get('title', '')[:40]}...")
                return True
            else:
                logger.warning(f"Telegram API failed ({resp.status_code}): {resp.text[:120]}")
        except Exception as e:
            logger.error(f"Error sending Telegram alert: {e}")

        return False

# Global instance
telegram_notifier = TelegramNotifier()
