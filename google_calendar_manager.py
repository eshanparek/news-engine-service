import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from urllib.parse import quote

logger = logging.getLogger("GoogleCalendarManager")

GCAL_CONFIG_FILE = "google_calendar_config.json"

class GoogleCalendarManager:
    """
    Manages dual Google Calendar Integration:
      1. Direct Google Calendar API sync (Service Account / OAuth credentials)
         with automated 1-hour prior reminders (popup & email).
      2. Dynamic One-Click 'Add to Google Calendar' URL generator for Telegram and UI.
      3. RFC 5545 iCalendar (.ics) generation with native 60-min VALARM reminder blocks.
    """
    def __init__(self):
        self.calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "").strip()
        self.service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json").strip()
        self.service_account_json_str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        self.enabled = os.getenv("ENABLE_GOOGLE_CALENDAR_SYNC", "true").lower() == "true"
        
        self.service = None
        self._load_config()
        self._init_service()

    def _load_config(self):
        if os.path.exists(GCAL_CONFIG_FILE):
            try:
                with open(GCAL_CONFIG_FILE, "r") as f:
                    cfg = json.load(f)
                if cfg.get("calendar_id"):
                    self.calendar_id = cfg["calendar_id"].strip()
                if cfg.get("service_account_file"):
                    self.service_account_file = cfg["service_account_file"].strip()
                if cfg.get("service_account_json_str"):
                    self.service_account_json_str = cfg["service_account_json_str"].strip()
                if "enabled" in cfg:
                    self.enabled = bool(cfg["enabled"])
            except Exception as e:
                logger.warning(f"Failed to load {GCAL_CONFIG_FILE}: {e}")

    def save_config(self, calendar_id: str, service_account_json_str: str = "", service_account_file: str = "", enabled: bool = True) -> Dict:
        self.calendar_id = calendar_id.strip()
        if service_account_json_str.strip():
            self.service_account_json_str = service_account_json_str.strip()
        if service_account_file.strip():
            self.service_account_file = service_account_file.strip()
        self.enabled = bool(enabled)

        payload = {
            "calendar_id": self.calendar_id,
            "service_account_file": self.service_account_file,
            "service_account_json_str": self.service_account_json_str,
            "enabled": self.enabled,
            "updated_at": datetime.now().isoformat()
        }
        try:
            with open(GCAL_CONFIG_FILE, "w") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving {GCAL_CONFIG_FILE}: {e}")

        self._init_service()
        return payload

    def _init_service(self):
        if not self.enabled or not self.calendar_id:
            self.service = None
            return

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds = None
            scopes = ['https://www.googleapis.com/auth/calendar']

            if self.service_account_json_str:
                service_info = json.loads(self.service_account_json_str)
                creds = service_account.Credentials.from_service_account_info(service_info, scopes=scopes)
            elif os.path.exists(self.service_account_file):
                creds = service_account.Credentials.from_service_account_file(self.service_account_file, scopes=scopes)

            if creds:
                self.service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
                logger.info(f"Google Calendar Service initialized successfully for {self.calendar_id}")
            else:
                self.service = None
        except Exception as e:
            logger.warning(f"Could not initialize Google Calendar API client: {e}")
            self.service = None

    def is_api_configured(self) -> bool:
        return bool(self.service and self.calendar_id)

    # ─────────────────────────────────────────────────────────────
    # 1. ONE-CLICK DYNAMIC GOOGLE CALENDAR LINK GENERATOR
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def generate_one_click_url(event: Dict) -> str:
        """
        Creates a pre-filled Google Calendar web URL:
        https://calendar.google.com/calendar/render?action=TEMPLATE&text=...&dates=...&details=...
        """
        date_str = event.get("date", "")
        time_str = event.get("time", "10:00")
        market = event.get("market", "NSE")
        symbol = event.get("symbol", market)
        event_name = event.get("event", "Economic Event")
        impact = event.get("impact", "HIGH")
        
        try:
            # Time in IST is UTC+05:30 -> Convert to UTC for standard Google Calendar dates parameter
            dt_ist = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            dt_utc_start = dt_ist - timedelta(hours=5, minutes=30)
            dt_utc_end = dt_utc_start + timedelta(minutes=45)
            dates_param = f"{dt_utc_start.strftime('%Y%m%dT%H%M%SZ')}/{dt_utc_end.strftime('%Y%m%dT%H%M%SZ')}"
        except Exception:
            dates_param = f"{date_str.replace('-', '')}/{date_str.replace('-', '')}"

        title = f"[{market} - {impact}] {symbol}: {event_name}"
        details = (
            f"Market: {market}\n"
            f"Symbol: {symbol}\n"
            f"Event: {event_name}\n"
            f"Time: {time_str} IST\n"
            f"Impact: {impact}\n"
            f"Previous: {event.get('previous', '—')} | Forecast: {event.get('forecast', '—')}\n"
            f"Details: {event.get('details', '')}\n\n"
            f"— Dispatched by EPM Pro News & Calendar Engine"
        )
        location = f"{market} Exchange / Financial Market"

        base_url = "https://calendar.google.com/calendar/render"
        url = (
            f"{base_url}?action=TEMPLATE"
            f"&text={quote(title)}"
            f"&dates={dates_param}"
            f"&details={quote(details)}"
            f"&location={quote(location)}"
        )
        return url

    # ─────────────────────────────────────────────────────────────
    # 2. DIRECT GOOGLE CALENDAR API SYNC (1-HOUR REMINDERS)
    # ─────────────────────────────────────────────────────────────
    def sync_event_to_google_calendar(self, event: Dict) -> tuple[bool, str]:
        """
        Directly syncs an event to Google Calendar via API with a 60-minute prior popup + email alarm.
        """
        if not self.is_api_configured():
            return False, "Google Calendar API is not configured or disabled."

        try:
            date_str = event.get("date", "")
            time_str = event.get("time", "10:00")
            dt_ist = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            # Google Calendar accepts ISO string with timezone offset (+05:30 for IST)
            iso_start = dt_ist.strftime("%Y-%m-%dT%H:%M:00+05:30")
            iso_end = (dt_ist + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:00+05:30")

            market = event.get("market", "NSE")
            symbol = event.get("symbol", market)
            event_name = event.get("event", "Market Event")
            impact = event.get("impact", "HIGH")
            summary = f"[{market} - {impact}] {symbol}: {event_name}"
            
            description = (
                f"Market: {market}\n"
                f"Symbol: {symbol}\n"
                f"Event: {event_name}\n"
                f"Time: {time_str} IST\n"
                f"Impact: {impact}\n"
                f"Previous: {event.get('previous', '—')} | Forecast: {event.get('forecast', '—')}\n"
                f"Actual: {event.get('actual', '⏳ Pending')} ({event.get('outcome_sentiment', '⏳ PENDING')})\n"
                f"Details: {event.get('details', '')}\n\n"
                f"— EPM Pro News & Calendar Engine"
            )

            event_body = {
                'summary': summary,
                'location': f"{market} Market",
                'description': description,
                'start': {
                    'dateTime': iso_start,
                    'timeZone': 'Asia/Kolkata',
                },
                'end': {
                    'dateTime': iso_end,
                    'timeZone': 'Asia/Kolkata',
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 60}, # 1 hour reminder!
                        {'method': 'email', 'minutes': 60}, # 1 hour reminder!
                    ],
                },
            }

            created_event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event_body
            ).execute()

            html_link = created_event.get('htmlLink', '')
            return True, html_link or "Created successfully"
        except Exception as e:
            logger.error(f"Error syncing event to Google Calendar: {e}")
            return False, str(e)

    def sync_events_batch(self, events: List[Dict]) -> tuple[int, int]:
        """
        Batch sync multiple events to Google Calendar.
        Returns: (success_count, fail_count)
        """
        if not self.is_api_configured():
            return 0, len(events)

        success = 0
        fail = 0
        for ev in events:
            ok, _ = self.sync_event_to_google_calendar(ev)
            if ok:
                success += 1
            else:
                fail += 1
        return success, fail

    # ─────────────────────────────────────────────────────────────
    # 3. ENHANCED RFC 5545 iCALENDAR (WITH 60-MIN VALARM)
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def generate_enhanced_ics(events: List[Dict]) -> str:
        """
        Generates standard RFC 5545 iCalendar feed with 60-minute prior VALARM blocks.
        """
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//EPM Pro//Multi-Market News & Calendar Engine//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:EPM Pro Multi-Market Calendar (NSE, BSE, MCX, Crypto, NYSE)",
            "X-WR-TIMEZONE:Asia/Kolkata"
        ]

        for ev in events:
            try:
                date_str = ev.get("date", "")
                time_str = ev.get("time", "10:00")
                dt_start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                dt_end = dt_start + timedelta(minutes=45)
                uid = f"{ev.get('id', 'ev')}@epmpro.market"
                mkt = ev.get("market", "NSE")
                impact = ev.get("impact", "HIGH")
                symbol = ev.get("symbol", mkt)
                event_name = ev.get("event", "Financial Catalyst")

                summary = f"[{mkt} - {impact}] {symbol}: {event_name}"
                desc = (
                    f"Market: {mkt}\\n"
                    f"Time: {time_str} IST\\n"
                    f"Previous: {ev.get('previous', '—')} | Forecast: {ev.get('forecast', '—')}\\n"
                    f"Actual: {ev.get('actual', '⏳ Pending')}\\n"
                    f"Verdict: {ev.get('outcome_sentiment', '⏳ PENDING')}\\n"
                    f"Details: {ev.get('details', '')}"
                )

                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTART:{dt_start.strftime('%Y%m%dT%H%M%S')}",
                    f"DTEND:{dt_end.strftime('%Y%m%dT%H%M%S')}",
                    f"SUMMARY:{summary}",
                    f"DESCRIPTION:{desc}",
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    "DESCRIPTION:Reminder: Market catalyst unfolds in 1 hour",
                    "TRIGGER:-PT60M", # 1 hour reminder!
                    "END:VALARM",
                    "END:VEVENT"
                ])
            except Exception:
                continue

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines)

google_calendar_manager = GoogleCalendarManager()
