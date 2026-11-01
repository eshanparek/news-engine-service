"""
Market Ticker Engine
Fetches live market quotes for SENSEX, NIFTY 50, INDIA VIX, BRENT CRUDE, GOLD, USD/INR, and DXY.
Maintains a resilient in-memory cache and updates in the background.
"""

import json
import logging
import ssl
import threading
import time
import urllib.request
from typing import Dict, List

logger = logging.getLogger("market_ticker")

TICKER_SYMBOLS = [
    {"label": "NIFTY 50", "sym": "^NSEI", "prefix": "", "suffix": "", "title": "Nifty 50 Index (NSE)"},
    {"label": "SENSEX", "sym": "^BSESN", "prefix": "", "suffix": "", "title": "BSE Sensex"},
    {"label": "INDIA VIX", "sym": "^INDIAVIX", "prefix": "", "suffix": "", "title": "India Volatility Index"},
    {"label": "BRENT", "sym": "BZ=F", "prefix": "$", "suffix": "", "title": "Brent Crude Oil Spot ($/bbl)"},
    {"label": "GOLD", "sym": "GC=F", "prefix": "$", "suffix": "", "title": "Spot Gold ($/oz)"},
    {"label": "USD/INR", "sym": "INR=X", "prefix": "₹", "suffix": "", "title": "US Dollar vs Indian Rupee"},
    {"label": "DXY", "sym": "DX-Y.NYB", "prefix": "", "suffix": "", "title": "US Dollar Index"}
]

# Baseline fallback in case network is down
_CACHE: List[Dict] = [
    {"sym": "NIFTY 50", "val": "24,850.35", "chg": "+0.42%", "dir": "up", "title": "Nifty 50 Index (NSE)"},
    {"sym": "SENSEX", "val": "81,420.10", "chg": "+0.38%", "dir": "up", "title": "BSE Sensex"},
    {"sym": "INDIA VIX", "val": "13.15", "chg": "-2.10%", "dir": "down", "title": "India Volatility Index"},
    {"sym": "BRENT", "val": "$74.20", "chg": "+0.54%", "dir": "up", "title": "Brent Crude Oil Spot ($/bbl)"},
    {"sym": "GOLD", "val": "$2,654.80", "chg": "+0.15%", "dir": "up", "title": "Spot Gold ($/oz)"},
    {"sym": "USD/INR", "val": "₹84.05", "chg": "-0.02%", "dir": "down", "title": "US Dollar vs Indian Rupee"},
    {"sym": "DXY", "val": "103.85", "chg": "+0.12%", "dir": "up", "title": "US Dollar Index"}
]
_LOCK = threading.Lock()
_LAST_UPDATE = 0


def fetch_live_quotes() -> List[Dict]:
    """Fetches real-time market quotes from Yahoo Finance API with unverified SSL context."""
    global _CACHE, _LAST_UPDATE
    ctx = ssl._create_unverified_context()
    fresh_items = []

    for item in TICKER_SYMBOLS:
        sym = item["sym"]
        label = item["label"]
        prefix = item["prefix"]
        suffix = item["suffix"]
        title = item["title"]

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1d"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=4, context=ctx) as resp:
                data = json.loads(resp.read().decode())
                meta = data["chart"]["result"][0]["meta"]
                price = meta.get("regularMarketPrice")
                prev = meta.get("previousClose") or meta.get("chartPreviousClose")
                if price is not None and prev is not None and prev > 0:
                    pct = ((price - prev) / prev) * 100
                    direction = "up" if pct >= 0 else "down"
                    sign = "+" if pct >= 0 else ""
                    
                    if label in ["NIFTY 50", "SENSEX", "GOLD"]:
                        val_str = f"{prefix}{price:,.2f}{suffix}"
                    elif label in ["BRENT", "USD/INR", "DXY", "INDIA VIX"]:
                        val_str = f"{prefix}{price:,.2f}{suffix}"
                    else:
                        val_str = f"{prefix}{price:.2f}{suffix}"

                    fresh_items.append({
                        "sym": label,
                        "val": val_str,
                        "chg": f"{sign}{pct:.2f}%",
                        "dir": direction,
                        "title": title
                    })
        except Exception as e:
            logger.debug(f"Ticker quote fetch failed for {sym}: {e}")

    if len(fresh_items) >= 4:
        with _LOCK:
            _CACHE = fresh_items
            _LAST_UPDATE = time.time()
        logger.info(f"Updated live market ticker with {len(fresh_items)} live quotes.")
    
    with _LOCK:
        return list(_CACHE)


def get_latest_ticker_quotes() -> List[Dict]:
    """Returns cached ticker quotes, refreshing in background if older than 30s."""
    global _LAST_UPDATE
    if time.time() - _LAST_UPDATE > 30:
        threading.Thread(target=fetch_live_quotes, daemon=True).start()
    with _LOCK:
        return list(_CACHE)


def get_ticker_track_html() -> str:
    """Generates the dual-set ticker track HTML with 1/2 character spacing."""
    quotes = get_latest_ticker_quotes()
    items_html = []
    for q in quotes:
        arrow = "▲ " if q.get("dir") == "up" else ("▼ " if q.get("dir") == "down" else "")
        items_html.append(f'''<div class="epm-ticker-item" title="{q.get('title', q['sym'])}">
    <span class="epm-ticker-sym">{q['sym']}</span>&nbsp;<span class="epm-ticker-val">{q['val']}</span>&nbsp;<span class="epm-ticker-chg {q.get('dir', 'up')}">{arrow}{q['chg']}</span>
</div>
<div class="epm-ticker-divider"></div>''')
    
    # Repeat twice for seamless infinite marquee loop
    full_track = "".join(items_html) * 2
    return full_track


# Trigger an immediate synchronous fetch on load
try:
    fetch_live_quotes()
except Exception:
    pass

