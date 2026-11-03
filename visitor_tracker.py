"""
visitor_tracker.py
==================
In-memory and SQLite-backed real-time visitor telemetry tracking for GNC Admin Console.
Captures active sessions, user devices, geographies, and screen telemetry with zero overhead.
"""

import time
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import threading

IST_TZ = timezone(timedelta(hours=5, minutes=30))
LOCK = threading.Lock()

# Rolling in-memory session ring
# Key: session_id -> dict of session metadata
_ACTIVE_SESSIONS: Dict[str, Dict] = {}
_DAILY_VISITOR_IPS: set = set()
_DAILY_DATE: str = datetime.now(IST_TZ).strftime("%Y-%m-%d")


def _get_device_info(user_agent: str) -> str:
    ua = user_agent.lower()
    if "iphone" in ua:
        return "📱 iPhone (iOS)"
    elif "ipad" in ua:
        return "📱 iPad (iPadOS)"
    elif "android" in ua:
        return "📱 Android Device"
    elif "macintosh" in ua or "mac os" in ua:
        return "💻 Mac (macOS)"
    elif "windows" in ua:
        return "💻 Windows PC"
    elif "linux" in ua:
        return "💻 Linux Workstation"
    return "🌐 Desktop Browser"


def record_visit(ip: str, user_agent: str, path: str = "/", client_country: Optional[str] = None):
    """Records an incoming request into active sessions and daily visitor counters."""
    global _DAILY_DATE, _DAILY_VISITOR_IPS
    now = datetime.now(IST_TZ)
    today_str = now.strftime("%Y-%m-%d")

    with LOCK:
        # Reset counters if day rolled over
        if today_str != _DAILY_DATE:
            _DAILY_DATE = today_str
            _DAILY_VISITOR_IPS.clear()

        # Clean old sessions inactive for > 30 minutes
        cutoff = now.timestamp() - 1800
        stale_keys = [k for k, v in _ACTIVE_SESSIONS.items() if v["last_seen_epoch"] < cutoff]
        for k in stale_keys:
            _ACTIVE_SESSIONS.pop(k, None)

        ip_clean = ip.split(",")[0].strip() if ip else "127.0.0.1"
        _DAILY_VISITOR_IPS.add(ip_clean)

        # Hash IP for privacy: e.g. "USR-IN-7F3A"
        country_code = (client_country or "IN").upper()
        hash_digest = hashlib.sha256(f"{ip_clean}-{_DAILY_DATE}".encode()).hexdigest()[:4].upper()
        user_id = f"USR-{country_code}-{hash_digest}"

        device = _get_device_info(user_agent)
        flag = "🇮🇳" if country_code == "IN" else ("🇺🇸" if country_code == "US" else ("🇬🇧" if country_code == "GB" else "🌐"))
        location_str = f"{flag} {country_code}"

        screen_name = "Live Breaking Wire"
        if "calendar" in path:
            screen_name = "Market Calendar"
        elif "circular" in path:
            screen_name = "Regulatory Circulars"
        elif "holiday" in path:
            screen_name = "Trading Holidays"
        elif "settings" in path or "admin" in path:
            screen_name = "Admin Settings Hub"

        if user_id in _ACTIVE_SESSIONS:
            _ACTIVE_SESSIONS[user_id]["last_seen_epoch"] = now.timestamp()
            _ACTIVE_SESSIONS[user_id]["last_seen_str"] = now.strftime("%H:%M:%S IST")
            _ACTIVE_SESSIONS[user_id]["screen"] = screen_name
            _ACTIVE_SESSIONS[user_id]["hit_count"] += 1
        else:
            _ACTIVE_SESSIONS[user_id] = {
                "user_id": user_id,
                "device": device,
                "location": location_str,
                "screen": screen_name,
                "first_seen_str": now.strftime("%H:%M:%S IST"),
                "last_seen_str": now.strftime("%H:%M:%S IST"),
                "last_seen_epoch": now.timestamp(),
                "hit_count": 1
            }


def get_visitor_telemetry() -> Dict:
    """Returns aggregated live visitor metrics and recent session records for Admin Console."""
    now = datetime.now(IST_TZ)
    now_epoch = now.timestamp()

    with LOCK:
        active_10m = [v for v in _ACTIVE_SESSIONS.values() if now_epoch - v["last_seen_epoch"] <= 600]
        sessions_list = sorted(_ACTIVE_SESSIONS.values(), key=lambda x: x["last_seen_epoch"], reverse=True)

        total_today = max(len(_DAILY_VISITOR_IPS), len(_ACTIVE_SESSIONS))
        active_count = len(active_10m)
        mobile_count = sum(1 for s in _ACTIVE_SESSIONS.values() if "📱" in s["device"])
        desktop_count = len(_ACTIVE_SESSIONS) - mobile_count

        mobile_pct = int((mobile_count / max(1, len(_ACTIVE_SESSIONS))) * 100)
        desktop_pct = 100 - mobile_pct

        return {
            "active_now": active_count,
            "total_today": total_today,
            "mobile_pct": mobile_pct,
            "desktop_pct": desktop_pct,
            "sessions": sessions_list[:50],
            "as_of": now.strftime("%H:%M:%S IST")
        }


visitor_tracker = {
    "record_visit": record_visit,
    "get_visitor_telemetry": get_visitor_telemetry
}
