import os
import json
import time
import logging
import requests
from typing import Dict, List, Optional

logger = logging.getLogger("TelegramNotifier")

ADMIN_SETTINGS_FILE = "admin_settings.json"


class TelegramNotifier:
    """
    Sends structured breaking news alerts and Market Calendar / Outcome alerts
    to separate configurable Telegram channels or groups.
    Supports per-market separate message dispatching for:
      - NSE, BSE, MCX, CRYPTO, NYSE
      - 7:00 AM IST Today's Snapshot (per market)
      - 7:05 AM IST Tomorrow's Lined-Up Snapshot (per market)
      - 7:00 AM IST Next-Day Trading Holiday Alert (per market)
      - Individual Happening / Unfolded Event Outcomes & T-15m Countdowns
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

        # Granular Calendar Automation Toggles
        self.alert_on_countdown = True         # T-15m reminder alert per event
        self.alert_on_outcome = True           # Individual event outcome / unfolding alert
        self.alert_on_linked_news = True       # Individual event linked breaking news alert
        self.auto_daily_today_7am = True       # 7:00 AM IST Today's complete snapshot (5 separate market msgs)
        self.auto_daily_tomorrow_705am = True  # 7:05 AM IST Tomorrow's lined-up snapshot (5 separate market msgs)
        self.auto_holiday_7am = True           # 7:00 AM IST Next-day trading holiday alert

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
                if "auto_daily_today_7am" in data:
                    self.auto_daily_today_7am = bool(data["auto_daily_today_7am"])
                if "auto_daily_tomorrow_705am" in data:
                    self.auto_daily_tomorrow_705am = bool(data["auto_daily_tomorrow_705am"])
                if "auto_holiday_7am" in data:
                    self.auto_holiday_7am = bool(data["auto_holiday_7am"])
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
        alert_on_linked_news: bool = True,
        auto_daily_today_7am: bool = True,
        auto_daily_tomorrow_705am: bool = True,
        auto_holiday_7am: bool = True
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
        self.auto_daily_today_7am = bool(auto_daily_today_7am)
        self.auto_daily_tomorrow_705am = bool(auto_daily_tomorrow_705am)
        self.auto_holiday_7am = bool(auto_holiday_7am)

        payload = {
            "news_bot_token": self.bot_token,
            "news_chat_id": self.chat_id,
            "news_enabled": self.enabled,
            "calendar_bot_token": self.calendar_bot_token,
            "calendar_chat_id": self.calendar_chat_id,
            "calendar_enabled": self.calendar_enabled,
            "alert_on_countdown": self.alert_on_countdown,
            "alert_on_outcome": self.alert_on_outcome,
            "alert_on_linked_news": self.alert_on_linked_news,
            "auto_daily_today_7am": self.auto_daily_today_7am,
            "auto_daily_tomorrow_705am": self.auto_daily_tomorrow_705am,
            "auto_holiday_7am": self.auto_holiday_7am
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
            resp = requests.post(url, json=payload, timeout=10)
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

    def send_calendar_alert(self, event: Dict, alert_type: str = "OUTCOME", formatted_html: Optional[str] = None) -> bool:
        """
        Dispatches an individual Calendar Event alert (T-15m Countdown, Live Unfolded Outcome, or Linked News)
        in the unified market reporting format to the dedicated Calendar Telegram Channel.
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
        linked_url = event.get("linked_news_url", "")

        if formatted_html:
            text = formatted_html
        else:
            # Fallback formatting if caller did not pass pre-rendered unified HTML
            market = event.get("market", "NSE").upper()
            title = event.get("event", "Market Event")
            symbol = event.get("symbol", market)
            date_str = event.get("date", "")
            time_str = event.get("time", "")
            timer_str = event.get("timer", "⚡ LIVE")
            impact = event.get("impact", "HIGH")
            previous = event.get("previous", "—")
            forecast = event.get("forecast", "—")
            actual = event.get("actual", "⏳ Pending")
            sentiment = event.get("outcome_sentiment", "⏳ PENDING")
            details = event.get("details", "")
            linked_title = event.get("linked_news_title", "")

            text = (
                f"📊 <b>[{market}] MARKET CALENDAR — {alert_type} UPDATE</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📌 <b>[{time_str} IST] {symbol} — {title}</b>\n"
                f"   🗓 <b>Date:</b> <code>{date_str}</code>  |  ⏱ <b>Timer:</b> <code>{timer_str}</code>\n"
                f"   ⚡ <b>Impact:</b> <b>{impact}</b>\n"
                f"   📉 <b>Prev:</b> <code>{previous}</code>  |  🎯 <b>Forecast:</b> <code>{forecast}</code>\n"
                f"   🏁 <b>Outcome:</b> <b>{actual}</b>  |  📊 <b>Verdict:</b> <b>{sentiment}</b>\n"
            )
            if details:
                text += f"   💡 <i>{details}</i>\n"
            if linked_title and linked_url:
                text += f"   📰 <b>Live Wire:</b> <a href='{linked_url}'>{linked_title}</a>\n"
            text += f"\n━━━━━━━━━━━━━━━━━━━━━━\n<i>— EPM PRO Market Calendar Engine ({market})</i>"

        ok, _ = self._send_raw_html(token, self.calendar_chat_id, text, preview=bool(linked_url))
        return ok

    def send_calendar_digest(self, summary_html: str) -> tuple[bool, str]:
        """Sends a single HTML calendar message to the Calendar Telegram Channel."""
        token = self.get_effective_calendar_token()
        if not token or not self.calendar_chat_id:
            return False, "Calendar Telegram Bot Token or Calendar Chat ID is not configured."
        return self._send_raw_html(token, self.calendar_chat_id, summary_html, preview=False)

    def send_calendar_messages_batch(self, messages: List[str]) -> tuple[bool, str]:
        """
        Sends multiple separate per-market messages sequentially (e.g. NSE, BSE, MCX, CRYPTO, NYSE)
        with a short spacing delay so Telegram preserves strict ordering without rate-limiting.
        """
        token = self.get_effective_calendar_token()
        if not token or not self.calendar_chat_id:
            return False, "Calendar Telegram Bot Token or Calendar Chat ID is not configured."

        sent_count = 0
        last_err = ""
        for msg in messages:
            if not msg or not msg.strip():
                continue
            ok, detail = self._send_raw_html(token, self.calendar_chat_id, msg, preview=False)
            if ok:
                sent_count += 1
            else:
                last_err = detail
            time.sleep(0.35)

        if sent_count > 0:
            return True, f"Delivered {sent_count}/{len(messages)} separate market messages"
        return False, last_err or "No messages sent"

    def send_test_alert(self, channel_type: str = "calendar") -> tuple[bool, str]:
        """Sends a test message to verify credentials from the Admin panel."""
        if channel_type == "calendar":
            token = self.get_effective_calendar_token()
            chat_id = self.calendar_chat_id
            msg = (
                "✅ <b>EPM PRO — MULTI-MARKET CALENDAR CHANNEL CONNECTED</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "Your dedicated <b>Market Calendar & Outcomes</b> Telegram channel is active!\n\n"
                "🏛 <b>Markets Covered (Sent Separately):</b>\n"
                "• 🇮🇳 <b>NSE</b> (Nifty, Corporate Results, RBI, India Macro)\n"
                "• 🇮🇳 <b>BSE</b> (Sensex, Board Filings, Corporate Actions)\n"
                "• ⛽ <b>MCX</b> (Gold, Silver, Crude Oil, NatGas, Base Metals)\n"
                "• ₿ <b>CRYPTO</b> (BTC/ETH ETFs, Options Expiry, Token Unlocks)\n"
                "• 🇺🇸 <b>NYSE</b> (Wall Street Earnings, Fed FOMC, US Macro)\n\n"
                "⏰ <b>Automated Daily Schedule (IST):</b>\n"
                "• <b>07:00 AM IST:</b> Today's Complete Calendar & Timer Snapshot (5 Separate Market Messages)\n"
                "• <b>07:00 AM IST:</b> Next-Day Trading Holiday Alert (1 Day Before Any Market Holiday)\n"
                "• <b>07:05 AM IST:</b> Tomorrow's Lined-Up Events Snapshot (5 Separate Market Messages)\n"
                "• <b>Live 24/7:</b> Individual Event Unfolding Outcomes, Linked News & T-15m Alerts"
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
