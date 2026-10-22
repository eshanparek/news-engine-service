import os
import re
import json
import time
import html
import logging
import threading
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

        # Granular Calendar Automation Toggles - strictly 7:00 AM daily snapshot only
        self.alert_on_countdown = False        # Disabled: No countdown spam
        self.alert_on_outcome = False          # Disabled: No individual outcome spam
        self.alert_on_linked_news = False      # Disabled: No linked news calendar alerts
        self.auto_daily_today_7am = True       # Enabled: 07:00 AM IST Today's complete snapshot
        self.auto_daily_tomorrow_705am = False # Disabled: Daily 7 AM only
        self.auto_holiday_7am = True           # Enabled: 07:00 AM IST Next-day trading holiday alert
        self.auto_weekly_fri_7am = False       # Disabled: No weekly blast
        self.auto_circulars_tg = False         # Disabled: Circulars separate
        self.send_as_photos = True             # Deliver morning calendar as high-definition infographic photos
        self.public_app_url = os.getenv("PUBLIC_APP_URL", "").strip()
        self._send_lock = threading.Lock()
        self._last_send_time = 0.0

        self._load_admin_settings()

    def get_public_url(self) -> str:
        url = (self.public_app_url or os.getenv("PUBLIC_APP_URL", "")).strip().rstrip("/")
        if not url:
            url = "https://news-engine-service.onrender.com"
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        return url

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
                else:
                    self.alert_on_countdown = False
                if "alert_on_outcome" in data:
                    self.alert_on_outcome = bool(data["alert_on_outcome"])
                else:
                    self.alert_on_outcome = False
                if "alert_on_linked_news" in data:
                    self.alert_on_linked_news = bool(data["alert_on_linked_news"])
                else:
                    self.alert_on_linked_news = False
                if "auto_daily_today_7am" in data:
                    self.auto_daily_today_7am = bool(data["auto_daily_today_7am"])
                else:
                    self.auto_daily_today_7am = True
                if "auto_daily_tomorrow_705am" in data:
                    self.auto_daily_tomorrow_705am = bool(data["auto_daily_tomorrow_705am"])
                else:
                    self.auto_daily_tomorrow_705am = False
                if "auto_holiday_7am" in data:
                    self.auto_holiday_7am = bool(data["auto_holiday_7am"])
                else:
                    self.auto_holiday_7am = True
                if "auto_circulars_tg" in data:
                    self.auto_circulars_tg = bool(data["auto_circulars_tg"])
                else:
                    self.auto_circulars_tg = False
                if "auto_weekly_fri_7am" in data:
                    self.auto_weekly_fri_7am = bool(data["auto_weekly_fri_7am"])
                elif "auto_weekly_mon_7am" in data:
                    self.auto_weekly_fri_7am = bool(data["auto_weekly_mon_7am"])
                else:
                    self.auto_weekly_fri_7am = False
                if "send_as_photos" in data:
                    self.send_as_photos = bool(data["send_as_photos"])
                if data.get("public_app_url"):
                    self.public_app_url = data["public_app_url"].strip()
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
        alert_on_countdown: bool = False,
        alert_on_outcome: bool = False,
        alert_on_linked_news: bool = False,
        auto_daily_today_7am: bool = True,
        auto_daily_tomorrow_705am: bool = False,
        auto_holiday_7am: bool = True,
        send_as_photos: bool = True,
        public_app_url: str = "",
        auto_weekly_fri_7am: bool = False,
        auto_circulars_tg: bool = False
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
        self.send_as_photos = bool(send_as_photos)
        self.public_app_url = public_app_url.strip()
        self.auto_weekly_fri_7am = bool(auto_weekly_fri_7am)
        self.auto_circulars_tg = bool(auto_circulars_tg)

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
            "auto_holiday_7am": self.auto_holiday_7am,
            "send_as_photos": self.send_as_photos,
            "public_app_url": self.public_app_url,
            "auto_weekly_fri_7am": self.auto_weekly_fri_7am,
            "auto_circulars_tg": self.auto_circulars_tg
        }
        try:
            with open(ADMIN_SETTINGS_FILE, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving admin_settings.json: {e}")
        return payload

    def get_effective_calendar_token(self) -> str:
        """Uses dedicated calendar bot token if provided, otherwise falls back to main bot token."""
        return (self.calendar_bot_token or self.bot_token).strip()

    def get_effective_calendar_chat_id(self) -> str:
        """Uses dedicated calendar chat ID if provided, otherwise falls back to main news chat ID."""
        return (self.calendar_chat_id or self.chat_id).strip()

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def is_calendar_configured(self) -> bool:
        token = self.get_effective_calendar_token()
        chat_id = self.get_effective_calendar_chat_id()
        return bool(token and chat_id)

    def _send_raw_html(self, token: str, chat_id: str, text: str, preview: bool = False) -> tuple[bool, str]:
        if not token or not chat_id:
            return False, "Missing Bot Token or Chat ID"
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        # Automatically split messages exceeding Telegram's 4096-char limit on clean paragraph/line boundaries
        max_len = 3800
        chunks: List[str] = []
        if len(text) <= max_len:
            chunks = [text]
        else:
            paragraphs = text.split("\n\n")
            current_chunk = ""
            for p in paragraphs:
                candidate = f"{current_chunk}\n\n{p}" if current_chunk else p
                if len(candidate) <= max_len:
                    current_chunk = candidate
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    if len(p) <= max_len:
                        current_chunk = p
                    else:
                        # Split very long single block by single newline
                        lines = p.split("\n")
                        sub_chunk = ""
                        for ln in lines:
                            sub_cand = f"{sub_chunk}\n{ln}" if sub_chunk else ln
                            if len(sub_cand) <= max_len:
                                sub_chunk = sub_cand
                            else:
                                if sub_chunk:
                                    chunks.append(sub_chunk)
                                sub_chunk = ln[:max_len]
                        current_chunk = sub_chunk
            if current_chunk:
                chunks.append(current_chunk)

        total_parts = len(chunks)
        last_err = ""
        sent_ok = False
        for idx, chunk in enumerate(chunks, 1):
            part_text = f"<i>[Part {idx}/{total_parts}]</i>\n{chunk}" if total_parts > 1 else chunk
            payload = {
                "chat_id": chat_id,
                "text": part_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": not preview
            }
            with self._send_lock:
                # Keep minimum 0.8s spacing between ANY telegram message to avoid 429 flood limits
                elapsed = time.time() - self._last_send_time
                if elapsed < 0.8:
                    time.sleep(0.8 - elapsed)

                for attempt in range(3):
                    try:
                        resp = requests.post(url, json=payload, timeout=12)
                        self._last_send_time = time.time()
                        if resp.status_code == 200:
                            sent_ok = True
                            break
                        elif resp.status_code == 429:
                            retry_after = 5
                            try:
                                retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
                            except Exception:
                                pass
                            logger.warning(f"Telegram Rate Limit (429): backing off for {retry_after + 1}s (attempt {attempt + 1}/3)...")
                            time.sleep(retry_after + 1)
                        elif resp.status_code == 400 and "can't parse entities" in resp.text.lower():
                            logger.warning(f"Telegram HTML parse error: {resp.text[:120]}, retrying without HTML formatting...")
                            plain_payload = dict(payload)
                            plain_payload.pop("parse_mode", None)
                            plain_payload["text"] = re.sub(r'<[^>]+>', '', part_text)
                            resp_plain = requests.post(url, json=plain_payload, timeout=12)
                            if resp_plain.status_code == 200:
                                sent_ok = True
                                break
                            else:
                                err_msg = resp_plain.text[:160]
                                logger.warning(f"Telegram plain fallback error ({resp_plain.status_code}): {err_msg}")
                                last_err = f"HTTP {resp_plain.status_code}: {err_msg}"
                                break
                        else:
                            err_msg = resp.text[:160]
                            logger.warning(f"Telegram API error ({resp.status_code}): {err_msg}")
                            last_err = f"HTTP {resp.status_code}: {err_msg}"
                            break
                    except Exception as e:
                        logger.error(f"Telegram connection error: {e}")
                        last_err = str(e)
                        time.sleep(1)

        if sent_ok:
            return True, "Delivered"
        return False, last_err or "Delivery failed"

    def send_photo(self, token: str, chat_id: str, photo_bytes: bytes, caption: str = "") -> tuple[bool, str]:
        """
        Uploads and dispatches an infographic image card to the target Telegram channel using sendPhoto API.
        """
        if not token or not chat_id:
            return False, "Missing Bot Token or Chat ID"

        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        files = {
            "photo": ("market_calendar.png", photo_bytes, "image/png")
        }
        data = {
            "chat_id": chat_id,
            "caption": caption[:1024],  # Telegram caption limit is 1024 chars
            "parse_mode": "HTML"
        }

        with self._send_lock:
            elapsed = time.time() - self._last_send_time
            if elapsed < 0.8:
                time.sleep(0.8 - elapsed)

            for attempt in range(3):
                try:
                    resp = requests.post(url, data=data, files=files, timeout=20)
                    self._last_send_time = time.time()
                    if resp.status_code == 200:
                        return True, "Delivered"
                    elif resp.status_code == 400 and "can't parse entities" in resp.text.lower():
                        logger.warning("Telegram HTML parse error, retrying without HTML formatting...")
                        data_plain = dict(data)
                        data_plain.pop("parse_mode", None)
                        data_plain["caption"] = re.sub(r'<[^>]+>', '', caption)[:1020]
                        resp_plain = requests.post(url, data=data_plain, files=files, timeout=20)
                        if resp_plain.status_code == 200:
                            return True, "Delivered (plain text fallback)"
                        err = resp_plain.text[:160]
                        logger.warning(f"Telegram sendPhoto plain error ({resp_plain.status_code}): {err}")
                        return False, f"HTTP {resp_plain.status_code}: {err}"
                    elif resp.status_code == 429:
                        retry_after = 5
                        try:
                            retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
                        except Exception:
                            pass
                        logger.warning(f"Telegram Photo Rate Limit (429): backing off {retry_after + 1}s...")
                        time.sleep(retry_after + 1)
                    else:
                        err = resp.text[:160]
                        logger.warning(f"Telegram sendPhoto error ({resp.status_code}): {err}")
                        return False, f"HTTP {resp.status_code}: {err}"
                except Exception as e:
                    logger.error(f"Telegram sendPhoto connection error: {e}")
                    time.sleep(1)

        return False, "Failed to send photo"

    def send_calendar_photo(self, photo_bytes: bytes, caption: str = "") -> tuple[bool, str]:
        """Dispatches an infographic card directly to the dedicated Calendar Telegram channel."""
        if not self.calendar_enabled or not self.is_calendar_configured():
            return False, "Calendar Telegram channel is disabled or not configured."
        token = self.get_effective_calendar_token()
        chat_id = self.get_effective_calendar_chat_id()
        return self.send_photo(token, chat_id, photo_bytes, caption)

    def send_calendar_photos_batch(self, photo_items: List[tuple]) -> tuple[bool, str]:
        """
        Sends multiple separate per-market infographic photo cards sequentially (e.g. NSE, BSE, MCX, CRYPTO, NYSE)
        with spacing delay to prevent Telegram 429 rate limits.
        Each item in photo_items is (photo_bytes, caption).
        """
        if not self.calendar_enabled or not self.is_calendar_configured():
            return False, "Calendar Telegram channel is disabled or not configured."

        token = self.get_effective_calendar_token()
        chat_id = self.get_effective_calendar_chat_id()
        if not token or not chat_id:
            return False, "Telegram Bot Token or Chat ID is not configured."

        sent_count = 0
        last_err = ""
        for photo_bytes, caption in photo_items:
            if not photo_bytes:
                continue
            ok, detail = self.send_photo(token, chat_id, photo_bytes, caption)
            if ok:
                sent_count += 1
            else:
                last_err = detail
            time.sleep(0.5)

        if sent_count > 0:
            return True, f"Delivered {sent_count}/{len(photo_items)} market infographic photo cards"
        return False, last_err or "No photo cards delivered"

    def send_news_alert(self, news: Dict) -> bool:
        if not self.enabled or not self.is_configured():
            logger.warning(f"[Telegram] News alert skipped: enabled={self.enabled}, bot_token={'SET' if self.bot_token else 'EMPTY'}, chat_id={'SET' if self.chat_id else 'EMPTY'}")
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

        safe_sectors = html.escape(", ".join(ai_sectors) if ai_sectors else "Broad Market")
        safe_title = html.escape(title)
        safe_source = html.escape(source)
        safe_reasoning = html.escape(ai_reasoning) if ai_reasoning else ""

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

        context_block = f"\n💡 <b>Analysis:</b> <i>{safe_reasoning}</i>" if safe_reasoning else ""

        text = (
            f"{header}\n\n"
            f"<b>{safe_title}</b>\n\n"
            f"{score_line}\n"
            f"📊 <b>Sentiment:</b> {sentiment_label}\n"
            f"🎯 <b>Affected:</b> {safe_sectors}"
            f"{context_block}\n\n"
            f"🏛 <b>Source:</b> {safe_source} | <b>Relevance:</b> {relevance}%\n"
            f"🔗 <a href='{link}'>Read Full Article</a>"
        )

        ok, err = self._send_raw_html(self.bot_token, self.chat_id, text, preview=True)
        if ok:
            logger.info(f"[Telegram] News alert successfully delivered: '{title[:50]}'")
        else:
            logger.error(f"[Telegram] News alert delivery failed ({err}): '{title[:50]}'")
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

        chat_id = self.get_effective_calendar_chat_id()
        if not token or not chat_id:
            logger.warning("No effective Telegram token or chat ID configured for calendar alert.")
            return False

        ok, _ = self._send_raw_html(token, chat_id, text, preview=bool(linked_url))
        return ok

    def send_calendar_digest(self, summary_html: str) -> tuple[bool, str]:
        """Sends a single HTML calendar message to the Calendar Telegram Channel (or fallback news channel)."""
        token = self.get_effective_calendar_token()
        chat_id = self.get_effective_calendar_chat_id()
        if not token or not chat_id:
            return False, "Telegram Bot Token or Chat ID is not configured."
        return self._send_raw_html(token, chat_id, summary_html, preview=False)

    def send_calendar_messages_batch(self, messages: List[str]) -> tuple[bool, str]:
        """
        Sends multiple separate per-market messages sequentially (e.g. NSE, BSE, MCX, CRYPTO, NYSE)
        with a short spacing delay so Telegram preserves strict ordering without rate-limiting.
        """
        token = self.get_effective_calendar_token()
        chat_id = self.get_effective_calendar_chat_id()
        if not token or not chat_id:
            return False, "Telegram Bot Token or Chat ID is not configured."

        sent_count = 0
        last_err = ""
        for msg in messages:
            if not msg or not msg.strip():
                continue
            ok, detail = self._send_raw_html(token, chat_id, msg, preview=False)
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
            chat_id = self.get_effective_calendar_chat_id()
            if not token or not chat_id:
                return False, "No Telegram Bot Token or Chat ID configured for Calendar (or fallback News)."
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
