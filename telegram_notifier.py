import os
import json
import time
import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger("TelegramNotifier")

ADMIN_SETTINGS_FILE = "admin_settings.json"

class TelegramNotifier:
    """
    Sends structured breaking news alerts and Market Calendar / Outcome alerts
    to separate configurable Telegram channels or groups.
    """
    def __init__(self):
        # 1. News Channel Credentials
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.enabled = os.getenv("ENABLE_TELEGRAM_ALERTS", "true").lower() == "true"

        # 2. Dedicated Calendar & Outcomes Channel Credentials
        self.calendar_bot_token = os.getenv("CALENDAR_TELEGRAM_BOT_TOKEN", "").strip()
        self.calendar_chat_id = os.getenv("CALENDAR_TELEGRAM_CHAT_ID", "").strip()
        self.calendar_enabled = os.getenv("ENABLE_CALENDAR_ALERTS", "true").lower() == "true"
        self.alert_on_countdown = True   # T-15m reminder alert
        self.alert_on_outcome = True     # Actual outcome release alert
        self.alert_on_linked_news = True # Linked breaking news alert

        self._load_admin_settings()

    def _load_admin_settings(self):
        if os.path.exists(ADMIN_SETTINGS_FILE):
            try:
                with open(ADMIN_SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                if data.get("news_bot_token"):
                    self.bot_token = data["news_bot_token"].strip()
                if data.get("news_chat_id"):
                    self.chat_id = data["news_chat_id"].strip()
                if "news_enabled" in data:
                    self.enabled = bool(data["news_enabled"])

                if data.get("calendar_bot_token"):
                    self.calendar_bot_token = data["calendar_bot_token"].strip()
                if data.get("calendar_chat_id"):
                    self.calendar_chat_id = data["calendar_chat_id"].strip()
                if "calendar_enabled" in data:
                    self.calendar_enabled = bool(data["calendar_enabled"])
                if "alert_on_countdown" in data:
                    self.alert_on_countdown = bool(data["alert_on_countdown"])
                if "alert_on_outcome" in data:
                    self.alert_on_outcome = bool(data["alert_on_outcome"])
                if "alert_on_linked_news" in data:
                    self.alert_on_linked_news = bool(data["alert_on_linked_news"])
                logger.info("Loaded Telegram & Calendar channel settings from admin_settings.json")
            except Exception as e:
                logger.warning(f"Failed to load admin_settings.json: {e}")

    def save_admin_settings(
        self,
        news_bot_token: str,
        news_chat_id: str,
        news_enabled: bool,
        calendar_bot_token: str,
        calendar_chat_id: str,
        calendar_enabled: bool,
        alert_on_countdown: bool = True,
        alert_on_outcome: bool = True,
        alert_on_linked_news: bool = True
    ) -> Dict:
        if news_bot_token.strip():
            self.bot_token = news_bot_token.strip()
        if news_chat_id.strip():
            self.chat_id = news_chat_id.strip()
        self.enabled = bool(news_enabled)

        self.calendar_bot_token = calendar_bot_token.strip()
        self.calendar_chat_id = calendar_chat_id.strip()
        self.calendar_enabled = bool(calendar_enabled)
        self.alert_on_countdown = bool(alert_on_countdown)
        self.alert_on_outcome = bool(alert_on_outcome)
        self.alert_on_linked_news = bool(alert_on_linked_news)

        payload = {
            "news_bot_token": self.bot_token,
            "news_chat_id": self.chat_id,
            "news_enabled": self.enabled,
            "calendar_bot_token": self.calendar_bot_token,
            "calendar_chat_id": self.calendar_chat_id,
            "calendar_enabled": self.calendar_enabled,
            "alert_on_countdown": self.alert_on_countdown,
            "alert_on_outcome": self.alert_on_outcome,
            "alert_on_linked_news": self.alert_on_linked_news
        }
        try:
            with open(ADMIN_SETTINGS_FILE, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving admin_settings.json: {e}")
        return payload

    def get_effective_calendar_token(self) -> str:
        """Uses dedicated calendar bot token if provided, otherwise falls back to main bot token."""
        return self.calendar_bot_token or self.bot_token

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def is_calendar_configured(self) -> bool:
        token = self.get_effective_calendar_token()
        return bool(token and self.calendar_chat_id)

    def _send_raw_html(self, token: str, chat_id: str, text: str, preview: bool = False) -> tuple[bool, str]:
        if not token or not chat_id:
            return False, "Missing Bot Token or Chat ID"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": not preview
        }
        try:
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                return True, "Delivered"
            else:
                err_msg = resp.text[:160]
                logger.warning(f"Telegram API error ({resp.status_code}): {err_msg}")
                return False, f"HTTP {resp.status_code}: {err_msg}"
        except Exception as e:
            logger.error(f"Telegram connection error: {e}")
            return False, str(e)

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

        is_high_impact = (ai_score >= 8) or (ai_impact == "HIGH") or (relevance >= 80)

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

        ok, _ = self._send_raw_html(self.bot_token, self.chat_id, text, preview=True)
        return ok

    def send_calendar_alert(self, event: Dict, alert_type: str = "OUTCOME") -> bool:
        """
        Dispatches Calendar Event alerts to the dedicated Calendar Telegram Channel.
        alert_type: 'COUNTDOWN' | 'OUTCOME' | 'LINKED_NEWS'
        """
        if not self.calendar_enabled or not self.is_calendar_configured():
            return False

        if alert_type == "COUNTDOWN" and not self.alert_on_countdown:
            return False
        if alert_type == "OUTCOME" and not self.alert_on_outcome:
            return False
        if alert_type == "LINKED_NEWS" and not self.alert_on_linked_news:
            return False

        token = self.get_effective_calendar_token()
        title = event.get("event", "Market Event")
        symbol = event.get("symbol", "GLOBAL")
        date_str = event.get("date", "")
        time_str = event.get("time", "")
        impact = event.get("impact", "HIGH")
        previous = event.get("previous", "—")
        forecast = event.get("forecast", "—")
        actual = event.get("actual", "Pending")
        sentiment = event.get("outcome_sentiment", "⏳ PENDING")
        details = event.get("details", "")
        linked_title = event.get("linked_news_title", "")
        linked_url = event.get("linked_news_url", "")

        impact_badge = "🔥 HIGH IMPACT" if impact == "HIGH" else ("⚡ MEDIUM IMPACT" if impact == "MEDIUM" else "📌 EVENT")

        if alert_type == "COUNTDOWN":
            header = (
                "⏰⏳ <b>UPCOMING CALENDAR EVENT (T-15 MINS)</b> ⏳⏰\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            body = (
                f"📌 <b>{title}</b>\n"
                f"🏷 <b>Asset / Region:</b> {symbol}  |  {impact_badge}\n"
                f"🕒 <b>Scheduled Time:</b> {date_str} at {time_str} IST\n\n"
                f"📉 <b>Previous:</b> <code>{previous}</code>\n"
                f"🎯 <b>Consensus Forecast:</b> <code>{forecast}</code>\n"
                f"⏳ <b>Status:</b> Releasing in ~15 minutes\n"
            )
            if details:
                body += f"\n💡 <i>{details}</i>"

        elif alert_type == "LINKED_NEWS":
            header = (
                "🔗📊 <b>CALENDAR EVENT — LIVE NEWS UPDATE</b> 📊🔗\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            body = (
                f"📌 <b>Event:</b> {title} ({symbol})\n"
                f"⚡ <b>Impact:</b> {impact_badge}\n\n"
                f"📉 <b>Previous:</b> <code>{previous}</code>  |  🎯 <b>Forecast:</b> <code>{forecast}</code>\n"
                f"🏁 <b>Outcome / Actual:</b> <b>{actual}</b>\n"
                f"📊 <b>Market Verdict:</b> <b>{sentiment}</b>\n\n"
                f"📰 <b>Linked Breaking News:</b>\n"
                f"<i>\"{linked_title}\"</i>\n"
                f"🔗 <a href='{linked_url}'>Read Full Coverage</a>"
            )
        else:
            # OUTCOME RELEASED
            header = (
                "🔔📊 <b>MARKET CALENDAR OUTCOME RELEASED</b> 📊🔔\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            body = (
                f"📌 <b>{title}</b>\n"
                f"🏷 <b>Asset / Region:</b> {symbol}  |  {impact_badge}\n"
                f"🕒 <b>Release Time:</b> {date_str} at {time_str} IST\n\n"
                f"📉 <b>Previous:</b> <code>{previous}</code>\n"
                f"🎯 <b>Forecast:</b> <code>{forecast}</code>\n"
                f"🏁 <b>Actual Outcome:</b> <b>{actual}</b>\n\n"
                f"📊 <b>Market Sentiment Verdict:</b> <b>{sentiment}</b>"
            )
            if details:
                body += f"\n💡 <b>Context:</b> <i>{details}</i>"
            if linked_title and linked_url:
                body += f"\n\n📰 <a href='{linked_url}'>{linked_title}</a>"

        text = f"{header}\n\n{body}"
        ok, _ = self._send_raw_html(token, self.calendar_chat_id, text, preview=bool(linked_url))
        return ok

    def send_calendar_digest(self, summary_html: str) -> tuple[bool, str]:
        """Sends a full daily/upcoming calendar digest to the Calendar Telegram Channel."""
        token = self.get_effective_calendar_token()
        if not token or not self.calendar_chat_id:
            return False, "Calendar Telegram Bot Token or Calendar Chat ID is not configured."
        return self._send_raw_html(token, self.calendar_chat_id, summary_html, preview=False)

    def send_test_alert(self, channel_type: str = "calendar") -> tuple[bool, str]:
        """Sends a test message to verify credentials from the Admin panel."""
        if channel_type == "calendar":
            token = self.get_effective_calendar_token()
            chat_id = self.calendar_chat_id
            msg = (
                "✅ <b>EPM PRO — CALENDAR CHANNEL CONNECTED</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Your dedicated <b>Market Calendar & Outcomes</b> Telegram channel is active!\n\n"
                "• ⏰ <b>Pre-Event Countdown Alerts (T-15m):</b> Enabled\n"
                "• 🏁 <b>Live Actual vs Forecast Outcomes:</b> Enabled\n"
                "• 🔗 <b>Linked Breaking News Updates:</b> Enabled"
            )
        else:
            token = self.bot_token
            chat_id = self.chat_id
            msg = (
                "✅ <b>EPM PRO — LIVE NEWS CHANNEL CONNECTED</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Your real-time breaking news & AI sentiment feed is active!"
            )
        return self._send_raw_html(token, chat_id, msg, preview=False)

# Global instance
telegram_notifier = TelegramNotifier()
