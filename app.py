import os
import time
import html
import re
import sqlite3
import json
from typing import Optional, List, Dict
from datetime import datetime
from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import gradio as gr

load_dotenv()

from news_worker import news_worker
from ai_analyzer import ai_analyzer
from telegram_notifier import telegram_notifier
from whatsapp_notifier import whatsapp_notifier
from calendar_engine import calendar_engine, now_ist, MARKETS_ORDER, MARKET_META
from google_calendar_manager import google_calendar_manager
from circular_engine import circular_engine, REGULATORS, REGULATOR_META

# 1. Start Background Scraper, Scorer & Multi-Market Calendar Timer Daemons
news_worker.start()
calendar_engine.start()
circular_engine.start()

# 2. FastAPI Machine-to-Machine Endpoints
app = FastAPI(
    title="EPM Pro Live News & Multi-Market Calendar Engine",
    description="Decoupled high-speed real-time news scraping, AI impact evaluation, Multi-Market Calendar (NSE, BSE, MCX, Crypto, NYSE), 7:00 AM / 7:05 AM IST daily dispatches, next-day holiday alerts, and live unfolding outcomes.",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

START_TIME = time.time()


class NewsItem(BaseModel):
    title: str
    summary: Optional[str] = ""
    source: Optional[str] = "Manual"


class CalendarEventUpdate(BaseModel):
    id: Optional[str] = ""
    market: Optional[str] = "NSE"
    date: str
    time: str
    symbol: str
    event: str
    impact: Optional[str] = "HIGH"
    previous: Optional[str] = "—"
    forecast: Optional[str] = "—"
    actual: Optional[str] = "⏳ Pending"
    sentiment: Optional[str] = "⚪ NEUTRAL"
    forward_telegram: Optional[bool] = True


class AdminTelegramConfig(BaseModel):
    news_bot_token: Optional[str] = ""
    news_chat_id: Optional[str] = ""
    news_enabled: Optional[bool] = True
    calendar_bot_token: Optional[str] = ""
    calendar_chat_id: Optional[str] = ""
    calendar_enabled: Optional[bool] = True
    alert_on_countdown: Optional[bool] = True
    alert_on_outcome: Optional[bool] = True
    alert_on_linked_news: Optional[bool] = True
    auto_daily_today_7am: Optional[bool] = True
    auto_daily_tomorrow_705am: Optional[bool] = True
    auto_holiday_7am: Optional[bool] = True


class GoogleCalendarConfig(BaseModel):
    calendar_id: str
    service_account_json_str: Optional[str] = ""
    service_account_file: Optional[str] = ""
    enabled: Optional[bool] = True


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": now_ist().isoformat(),
        "cached_news": len(news_worker.news_cache),
        "calendar_events": len(calendar_engine.events),
        "markets": MARKETS_ORDER
    }


@app.get("/ping")
def ping():
    """Lightweight keep-alive endpoint for cron services (UptimeRobot, cron-job.org)."""
    return {
        "status": "pong",
        "timestamp_ist": now_ist().strftime("%Y-%m-%d %H:%M:%S IST"),
        "calendar_events": len(calendar_engine.events),
        "news_items": len(news_worker.news_cache)
    }


@app.get("/api/news")
def get_news(
    limit: int = Query(40, ge=1, le=100),
    min_relevance: int = Query(0, ge=0, le=100),
    source: Optional[str] = None,
    search: Optional[str] = None
):
    items = list(news_worker.news_cache)

    if min_relevance > 0:
        items = [x for x in items if x.get("relevance", 0) >= min_relevance]

    if source:
        src_lower = source.lower()
        items = [x for x in items if src_lower in x.get("source", "").lower()]

    if search:
        q = search.lower()
        items = [x for x in items if q in x.get("title", "").lower() or q in x.get("summary", "").lower()]

    return {
        "count": len(items[:limit]),
        "total_cached": len(news_worker.news_cache),
        "last_fetch": news_worker.last_fetch_time.isoformat() if news_worker.last_fetch_time else None,
        "news": items[:limit]
    }


@app.get("/api/sources")
def get_sources():
    return {
        "total": len(news_worker.sources),
        "sources": news_worker.sources
    }


@app.post("/api/trigger")
def trigger_fetch(background_tasks: BackgroundTasks):
    background_tasks.add_task(news_worker.poll_cycle)
    return {"status": "triggered", "message": "News poll cycle triggered in background."}


@app.post("/api/rate")
def rate_headline(item: NewsItem):
    res = ai_analyzer.analyze_news(item.title, item.summary or item.title, item.source or "Custom")
    return res


# ─── Calendar & Sync REST API Endpoints ──────────────────────────────────────

@app.get("/api/calendar")
def get_calendar(
    range_filter: str = Query("all", alias="range"),
    market_filter: str = Query("ALL", alias="market")
):
    events = calendar_engine.get_enriched_events(filter_range=range_filter, market_filter=market_filter)
    return {
        "status": "success",
        "as_of_ist": now_ist().strftime("%Y-%m-%d %H:%M:%S IST"),
        "markets": MARKETS_ORDER,
        "count": len(events),
        "events": events
    }


@app.get("/api/calendar/unified")
def get_unified_calendar():
    """Unified endpoint compatible with Trading Terminal v34_core.js and external clients."""
    holidays = calendar_engine.get_holiday_snapshot()
    events = calendar_engine.get_enriched_events(filter_range="all", market_filter="ALL")
    corporate_formatted = []
    for e in events:
        outcome_str = f"Prev: {e['previous']} | Est: {e['forecast']} → Actual: {e['actual']} ({e['outcome_sentiment']})"
        if e.get("linked_news_title"):
            outcome_str += f" | 🔗 {e['linked_news_title']}"
        corporate_formatted.append({
            "id": e["id"],
            "market": e.get("market", "NSE"),
            "symbol": e["symbol"],
            "event": f"[{e.get('market', 'NSE')}] {e['event']} [{e['timer']}]",
            "date": e["date"],
            "time": e["time"],
            "timer": e["timer"],
            "impact": e["impact"],
            "details": e.get("details", ""),
            "previous": e["previous"],
            "forecast": e["forecast"],
            "actual": e["actual"],
            "outcome_sentiment": e["outcome_sentiment"],
            "linked_news_title": e.get("linked_news_title", ""),
            "linked_news_url": e.get("linked_news_url", ""),
            "outcome_details": outcome_str,
            "status": "UNFOLDED" if e["status"] == "COMPLETED" else "PENDING",
            "unfold_ltp": 0,
            "live_ltp": 0
        })
    holidays["corporate_events"] = corporate_formatted
    holidays["events"] = events
    return holidays


@app.post("/api/calendar/sync")
def sync_calendar():
    calendar_engine.sync_all_calendars()
    return {
        "status": "synced",
        "total_events": len(calendar_engine.events),
        "synced_at": now_ist().strftime("%Y-%m-%d %H:%M:%S IST")
    }


@app.post("/api/calendar/dispatch/today")
def api_dispatch_today():
    ok, msg = calendar_engine.dispatch_all_markets_today_snapshot()
    return {"status": "success" if ok else "error", "detail": msg}


@app.post("/api/calendar/dispatch/today-photo")
def api_dispatch_today_photo():
    ok, msg = calendar_engine.dispatch_all_markets_today_photo_snapshot()
    return {"status": "success" if ok else "error", "detail": msg}


@app.post("/api/calendar/dispatch/tomorrow")
def api_dispatch_tomorrow():
    ok, msg = calendar_engine.dispatch_all_markets_tomorrow_snapshot()
    return {"status": "success" if ok else "error", "detail": msg}


@app.post("/api/calendar/dispatch/tomorrow-photo")
def api_dispatch_tomorrow_photo():
    ok, msg = calendar_engine.dispatch_all_markets_tomorrow_photo_snapshot()
    return {"status": "success" if ok else "error", "detail": msg}


@app.post("/api/calendar/dispatch/holiday")
def api_dispatch_holiday():
    ok, msg = calendar_engine.dispatch_next_day_holiday_alerts(force_preview=True)
    return {"status": "success" if ok else "error", "detail": msg}


@app.post("/api/calendar/dispatch/weekly")
def api_dispatch_weekly():
    ok, msg = calendar_engine.dispatch_weekly_calendar_message()
    return {"status": "success" if ok else "error", "detail": msg}


@app.get("/api/calendar/ics", response_class=PlainTextResponse)
def download_calendar_ics(
    range_filter: str = Query("all", alias="range"),
    market_filter: str = Query("ALL", alias="market")
):
    """iCal (.ics) subscription endpoint for Google Calendar, Apple Calendar & Outlook."""
    events = calendar_engine.get_enriched_events(filter_range=range_filter, market_filter=market_filter)
    ics_content = google_calendar_manager.generate_enhanced_ics(events)
    return PlainTextResponse(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f"attachment; filename=epm_market_calendar_{range_filter}.ics"}
    )


@app.post("/api/calendar/google/sync")
def api_sync_google_calendar():
    """Batch synchronizes all active market events to the target Google Calendar ID with 1-hr reminder alerts."""
    events = calendar_engine.get_enriched_events(filter_range="all", market_filter="ALL")
    success, fail = google_calendar_manager.sync_events_batch(events)
    return {
        "status": "completed",
        "synced": success,
        "failed": fail,
        "total": len(events),
        "calendar_id": google_calendar_manager.calendar_id,
        "is_configured": google_calendar_manager.is_api_configured()
    }


@app.post("/api/calendar/google/config")
def api_save_google_calendar_config(cfg: GoogleCalendarConfig):
    saved = google_calendar_manager.save_config(
        calendar_id=cfg.calendar_id,
        service_account_json_str=cfg.service_account_json_str or "",
        service_account_file=cfg.service_account_file or "",
        enabled=bool(cfg.enabled)
    )
    return {"status": "saved", "config": saved, "is_configured": google_calendar_manager.is_api_configured()}


@app.post("/api/calendar/event")
def upsert_calendar_event(payload: CalendarEventUpdate):
    ev = calendar_engine.update_or_add_event(
        event_id=payload.id or "",
        date_str=payload.date,
        time_str=payload.time,
        symbol=payload.symbol,
        event_name=payload.event,
        impact=payload.impact or "HIGH",
        previous=payload.previous or "—",
        forecast=payload.forecast or "—",
        actual=payload.actual or "⏳ Pending",
        sentiment=payload.sentiment or "⚪ NEUTRAL",
        market=payload.market or "AUTO",
        forward_now=bool(payload.forward_telegram)
    )
    return {"status": "success", "event": ev}


@app.get("/api/admin/settings")
def get_admin_settings():
    return {
        "news_chat_id": telegram_notifier.chat_id,
        "news_enabled": telegram_notifier.enabled,
        "news_configured": telegram_notifier.is_configured(),
        "calendar_chat_id": telegram_notifier.calendar_chat_id,
        "effective_calendar_chat_id": telegram_notifier.get_effective_calendar_chat_id(),
        "using_news_chat_as_calendar_fallback": not bool(telegram_notifier.calendar_chat_id) and bool(telegram_notifier.chat_id),
        "calendar_enabled": telegram_notifier.calendar_enabled,
        "calendar_configured": telegram_notifier.is_calendar_configured(),
        "alert_on_countdown": telegram_notifier.alert_on_countdown,
        "alert_on_outcome": telegram_notifier.alert_on_outcome,
        "alert_on_linked_news": telegram_notifier.alert_on_linked_news,
        "auto_daily_today_7am": telegram_notifier.auto_daily_today_7am,
        "auto_daily_tomorrow_705am": telegram_notifier.auto_daily_tomorrow_705am,
        "auto_holiday_7am": telegram_notifier.auto_holiday_7am,
        "google_calendar_id": google_calendar_manager.calendar_id,
        "google_calendar_enabled": google_calendar_manager.enabled,
        "google_calendar_configured": google_calendar_manager.is_api_configured()
    }


@app.post("/api/admin/settings")
def update_admin_settings(cfg: AdminTelegramConfig):
    saved = telegram_notifier.save_admin_settings(
        news_bot_token=cfg.news_bot_token or "",
        news_chat_id=cfg.news_chat_id or "",
        news_enabled=bool(cfg.news_enabled),
        calendar_bot_token=cfg.calendar_bot_token or "",
        calendar_chat_id=cfg.calendar_chat_id or "",
        calendar_enabled=bool(cfg.calendar_enabled),
        alert_on_countdown=bool(cfg.alert_on_countdown),
        alert_on_outcome=bool(cfg.alert_on_outcome),
        alert_on_linked_news=bool(cfg.alert_on_linked_news),
        auto_daily_today_7am=bool(cfg.auto_daily_today_7am),
        auto_daily_tomorrow_705am=bool(cfg.auto_daily_tomorrow_705am),
        auto_holiday_7am=bool(cfg.auto_holiday_7am)
    )
    return {"status": "saved", "settings": saved}


# ─── 3. Gradio Web Interface Functions & 2035 Terminal HTML Generators ─────

def clean_table_text(text: any) -> str:
    """Removes HTML tags, unescapes entities, and collapses whitespace for crisp table display."""
    if text is None:
        return ""
    # Strip HTML tags
    clean = re.sub(r'<[^>]+>', '', str(text))
    # Unescape HTML entities
    clean = html.unescape(clean)
    # Collapse multiple whitespaces/newlines to a single space
    clean = " ".join(clean.split())
    return clean.strip()


def render_news_feed_html(items: List[Dict]) -> str:
    """Renders 2035 Bloomberg-style visual news feed with glowing pills and AI impact scores on pure white canvas."""
    if not items:
        return (
            '<div class="epm-empty-state">'
            '  <div class="epm-empty-icon">📡</div>'
            '  <div class="epm-empty-title">Connecting to Global Multi-Market Financial Wire...</div>'
            '  <div class="epm-empty-sub">Ingesting real-time feeds from NSE, BSE, Bloomberg, Reuters, MCX, Crypto & SEC.</div>'
            '</div>'
        )

    cards_html = []
    for item in items[:40]:
        score = item.get("ai_score", 5)
        sent = str(item.get("ai_sentiment", "NEUTRAL")).upper()
        impact = str(item.get("ai_impact", "MEDIUM")).upper()
        title = html.escape(str(item.get("title", "")))
        source = html.escape(str(item.get("source", "Market Wire")))
        link = item.get("link", "#")
        time_str = html.escape(str(item.get("timestamp", ""))[:19])
        reasoning = html.escape(str(item.get("ai_reasoning", "")))
        sectors = item.get("ai_sectors", [])
        rel = item.get("relevance", 75)

        sent_class = "bullish" if "BULL" in sent else ("bearish" if "BEAR" in sent else "neutral")
        is_high = impact == "HIGH" or score >= 8
        impact_badge = f'<span class="epm-badge impact-{"high" if is_high else impact.lower()}">{"🔥 HIGH IMPACT" if is_high else ("⚡ MEDIUM" if impact == "MEDIUM" else "LOW")}</span>'
        score_badge = f'<span class="epm-score-pill">AI {score}/10</span>'
        sent_badge = f'<span class="epm-badge sent-{sent_class}">{sent}</span>'

        sector_pills = "".join(f'<span class="epm-sector-tag">{html.escape(str(s))}</span>' for s in sectors[:3]) if sectors else ""

        card = f'''
        <div class="epm-card epm-news-card {sent_class}">
            <div class="epm-card-header">
                <div class="epm-meta-left">
                    <span class="epm-source-chip">{source}</span>
                    <span class="epm-time-chip">⏱ {time_str}</span>
                    {impact_badge}
                    {sent_badge}
                </div>
                <div class="epm-meta-right">
                    {score_badge}
                </div>
            </div>
            <div class="epm-card-body">
                <a href="{link}" target="_blank" class="epm-news-title">{title} <span class="epm-link-icon">↗</span></a>
                {f'<div class="epm-news-reasoning">{reasoning}</div>' if reasoning else ""}
            </div>
            <div class="epm-card-footer">
                <div class="epm-sectors-wrap">{sector_pills}</div>
                <div class="epm-rel-badge">Relevance: <b>{rel}%</b></div>
            </div>
        </div>
        '''
        cards_html.append(card)

    return f'<div class="epm-stream-container">{"".join(cards_html)}</div>'


def render_circulars_feed_html(circulars: List[Dict]) -> str:
    """Renders ultra-modern institutional regulatory circular cards with 3-5 AI bullets and direct PDF action links."""
    if not circulars:
        return (
            '<div class="epm-empty-state">'
            '  <div class="epm-empty-icon">📜</div>'
            '  <div class="epm-empty-title">No Official Circulars Found For This Filter</div>'
            '  <div class="epm-empty-sub">Select another regulator or clear your search term to view official documents.</div>'
            '</div>'
        )

    cards = []
    for c in circulars:
        reg = c.get("regulator", "NSE")
        meta = REGULATOR_META.get(reg, {"badge": reg, "color": "#2563eb", "type": "Regulator"})
        title = html.escape(str(c.get("title", "")))
        circ_no = html.escape(str(c.get("circular_no", "")))
        date_str = html.escape(str(c.get("date", "")))
        pdf_url = c.get("pdf_url") or c.get("web_url", "#")
        category = html.escape(str(c.get("category", "Regulatory Disclosure")))
        impact = str(c.get("impact", "MEDIUM")).upper()
        bullets = c.get("bullets", [])
        action = html.escape(str(c.get("action_takeaway", "")))

        is_high = impact == "HIGH"
        impact_badge = f'<span class="epm-badge impact-{"high" if is_high else "medium"}">{"🚨 CRITICAL IMPACT" if is_high else "📌 OFFICIAL DIRECTIVE"}</span>'

        bullet_items = "".join(f'<li>{html.escape(str(b))}</li>' for b in bullets) if bullets else f'<li>{title}</li>'

        card = f'''
        <div class="epm-card epm-circ-card regulator-{reg.lower()} {'is-high-impact' if is_high else ''}">
            <div class="epm-card-header">
                <div class="epm-meta-left">
                    <span class="epm-reg-chip reg-{reg.lower()}">{meta['badge']}</span>
                    <span class="epm-circ-no"><code>{circ_no}</code></span>
                    <span class="epm-time-ist">📅 <b>{date_str}</b></span>
                    {impact_badge}
                </div>
                <div class="epm-meta-right">
                    <a href="{pdf_url}" target="_blank" class="epm-pdf-btn">📄 Open Official PDF ↗</a>
                </div>
            </div>
            <div class="epm-card-body">
                <div class="epm-circ-title-row">
                    <span class="epm-circ-title">{title}</span>
                </div>
                <div class="epm-circ-bullets-box">
                    <div class="epm-circ-bullets-head">🧠 <b>Institutional Impact & Actionable Breakdown (AI 3-5 Bullets):</b></div>
                    <ul class="epm-circ-bullets-list">
                        {bullet_items}
                    </ul>
                </div>
                {f'<div class="epm-circ-action">⚡ <b>Operational Takeaway:</b> {action}</div>' if action else ''}
            </div>
            <div class="epm-card-footer">
                <div class="epm-circ-cat">Classification: <b>{category}</b></div>
                <div class="epm-circ-verified">✅ Verified Document-Backed Release</div>
            </div>
        </div>
        '''
        cards.append(card)

    return f'<div class="epm-stream-container">{"".join(cards)}</div>'


def get_circulars_view(regulator_filter: str = "ALL", impact_filter: str = "ALL", search_query: str = ""):
    try:
        items = circular_engine.get_circulars(
            regulator_filter=regulator_filter,
            impact_filter=impact_filter,
            search_query=search_query
        )
        visual_html = render_circulars_feed_html(items)
        
        table_rows = []
        for it in items:
            meta = REGULATOR_META.get(it.get("regulator", "NSE"), {"badge": it.get("regulator", "NSE")})
            pdf_link = it.get("pdf_url") or it.get("web_url") or ""
            if pdf_link:
                pdf_display = f"[📄 Open PDF ↗]({pdf_link})"
            else:
                pdf_display = "—"
            bullets = it.get("bullets", []) or []
            cleaned_bullets = [clean_table_text(b) for b in bullets if b]
            if cleaned_bullets:
                bullets_text = " • ".join(cleaned_bullets)
            else:
                bullets_text = clean_table_text(it.get("action_takeaway") or it.get("title", "—"))
            if len(bullets_text) > 160:
                bullets_text = bullets_text[:160] + "..."

            clean_circ_title = clean_table_text(it.get("title", "—"))
            if len(clean_circ_title) > 140:
                clean_circ_title = clean_circ_title[:140] + "..."
            safe_title = clean_circ_title.replace("[", "(").replace("]", ")")
            title_display = f"[{safe_title}]({pdf_link})" if pdf_link else safe_title

            table_rows.append([
                meta.get("badge", it.get("regulator", "NSE")),
                clean_table_text(it.get("circular_no", "—")),
                clean_table_text(it.get("date", "—")),
                clean_table_text(it.get("impact", "MEDIUM")),
                title_display,
                clean_table_text(it.get("category", "Circular")),
                bullets_text,
                pdf_display
            ])
        
        if not table_rows:
            table_rows.append(["-", "-", "-", "-", "No official circulars matching current filters", "-", "-", "-"] )

        summary_text = (
            f"🏛️ **Authority Filter:** `{regulator_filter}` &nbsp;|&nbsp; "
            f"🚨 **Impact Filter:** `{impact_filter}` &nbsp;|&nbsp; "
            f"📜 **Official Documents Indexed:** `{len(items)}` &nbsp;|&nbsp; "
            f"🔒 **Storage:** Verified PDF Repository"
        )
        return summary_text, visual_html, table_rows
    except Exception as e:
        empty_rows = [["-", "-", "-", "-", f"Failed to load circulars: {str(e)}", "-", "-", "-"]]
        return f"⚠️ **Error loading circulars:** {str(e)}", f'<div class="epm-empty-state"><div class="epm-empty-icon">⚠️</div><div class="epm-empty-title">Error Loading Circulars</div><div class="epm-empty-sub">{str(e)}</div></div>', empty_rows


def refresh_circulars_data(regulator_filter: str = "ALL", impact_filter: str = "ALL", search_query: str = ""):
    try:
        circular_engine.poll_all_regulators()
    except Exception as e:
        print(f"[Circulars] Manual poll error: {e}")
    return get_circulars_view(regulator_filter, impact_filter, search_query)


def dispatch_circular_to_telegram(regulator_filter: str = "ALL"):
    try:
        with circular_engine._lock:
            with sqlite3.connect(circular_engine.db_path) as conn:
                conn.row_factory = sqlite3.Row
                if regulator_filter and regulator_filter != "ALL":
                    row = conn.execute(
                        "SELECT * FROM circulars WHERE regulator = ? ORDER BY timestamp DESC LIMIT 1",
                        (regulator_filter.upper(),)
                    ).fetchone()
                else:
                    row = conn.execute("SELECT * FROM circulars ORDER BY timestamp DESC LIMIT 1").fetchone()
                
                if not row:
                    return f"⚠️ No circulars available to dispatch for authority `{regulator_filter}`."
                
                bullets = json.loads(row["bullets_json"]) if row["bullets_json"] else []
                msg = circular_engine.format_telegram_circular_alert(
                    regulator=row["regulator"],
                    circ_no=row["circular_no"],
                    title=row["title"],
                    pdf_url=row["pdf_url"] or row["web_url"],
                    category=row["category"],
                    bullets=bullets,
                    action_takeaway=row["action_takeaway"]
                )
                ok, err = telegram_notifier.send_calendar_alert(msg)
                if ok:
                    return f"✅ **Dispatched Official [{row['regulator']}] Circular `{row['circular_no']}` with 3-5 Bullets & PDF Link to Telegram!**"
                return f"⚠️ **Telegram Dispatch Error:** {err} *(Verify Calendar Telegram Chat ID in Tab 4)*"
    except Exception as e:
        return f"⚠️ **Dispatch Exception:** {str(e)}"


def render_calendar_feed_html(events: List[Dict]) -> str:
    """Renders 2035 multi-market interactive catalyst cards with live countdown timers and 1-click Google Calendar sync."""
    if not events:
        return (
            '<div class="epm-empty-state">'
            '  <div class="epm-empty-icon">📅</div>'
            '  <div class="epm-empty-title">No Scheduled Catalysts Found For This Filter</div>'
            '  <div class="epm-empty-sub">Switch the market or time window filter above to explore scheduled corporate releases.</div>'
            '</div>'
        )

    cards_html = []
    for ev in events[:60]:
        mkt = str(ev.get("market", "NSE")).upper()
        meta = MARKET_META.get(mkt, MARKET_META["NSE"])
        sym = html.escape(str(ev.get("symbol", mkt)))
        name = html.escape(str(ev.get("event", "Scheduled Release")))
        date_str = html.escape(str(ev.get("date", "")))
        time_str = html.escape(str(ev.get("time", "10:00")))
        timer = html.escape(str(ev.get("timer", "⚡ LIVE")))
        impact = str(ev.get("impact", "HIGH")).upper()
        prev = html.escape(str(ev.get("previous", "—")))
        fore = html.escape(str(ev.get("forecast", "—")))
        actual = html.escape(str(ev.get("actual", "⏳ Pending")))
        sent = html.escape(str(ev.get("outcome_sentiment", "⏳ PENDING")))
        linked_title = html.escape(str(ev.get("linked_news_title", "")))
        linked_url = ev.get("linked_news_url", "")

        is_high = impact == "HIGH"
        impact_badge = f'<span class="epm-badge impact-{"high" if is_high else "medium"}">{"🔥 HIGH IMPACT BENCHMARK" if is_high else "⚡ MEDIUM"}</span>'
        sent_class = "bullish" if "BULL" in sent else ("bearish" if "BEAR" in sent else ("pending" if "PEND" in sent else "neutral"))

        # Compact one-click Google Calendar URL
        gcal_url = google_calendar_manager.generate_one_click_url(ev)

        timer_upper = timer.upper()
        timer_class = "timer-live" if "LIVE" in timer_upper else ("timer-done" if "RELEASED" in timer_upper or "PAST" in timer_upper else "timer-active")

        linked_snippet = ""
        if linked_title and linked_url:
            linked_snippet = f'<div class="epm-linked-news">🔗 <b>Breaking Wire Link:</b> <a href="{linked_url}" target="_blank">{linked_title} ↗</a></div>'

        card = f'''
        <div class="epm-card epm-cal-card market-{mkt.lower()} {'is-high-impact' if is_high else ''}">
            <div class="epm-card-header">
                <div class="epm-meta-left">
                    <span class="epm-mkt-chip mkt-{mkt.lower()}">{meta['badge']}</span>
                    <span class="epm-time-ist"><b>{time_str} IST</b>  •  <code>{date_str}</code></span>
                    <span class="epm-timer-pill {timer_class}">⏱ {timer}</span>
                    {impact_badge}
                </div>
                <div class="epm-meta-right">
                    <a href="{gcal_url}" target="_blank" class="epm-gcal-btn">📅 + Google Calendar</a>
                </div>
            </div>
            <div class="epm-card-body">
                <div class="epm-cal-title-row">
                    <span class="epm-sym-pill">{sym}</span>
                    <span class="epm-cal-name">{name}</span>
                </div>
                <div class="epm-metrics-grid">
                    <div class="epm-metric-box">
                        <span class="epm-m-label">PREVIOUS</span>
                        <span class="epm-m-val">{prev}</span>
                    </div>
                    <div class="epm-metric-box">
                        <span class="epm-m-label">CONSENSUS</span>
                        <span class="epm-m-val">{fore}</span>
                    </div>
                    <div class="epm-metric-box epm-actual-box">
                        <span class="epm-m-label">ACTUAL / OUTCOME</span>
                        <span class="epm-m-val">{actual}</span>
                    </div>
                    <div class="epm-metric-box epm-verdict-box">
                        <span class="epm-m-label">MARKET VERDICT</span>
                        <span class="epm-badge sent-{sent_class}">{sent}</span>
                    </div>
                </div>
                {linked_snippet}
            </div>
        </div>
        '''
        cards_html.append(card)

    return f'<div class="epm-stream-container">{"".join(cards_html)}</div>'


def get_dashboard_tables():
    try:
        items = list(news_worker.news_cache)
        top_rows = []
        bottom_rows = []

        for it in items:
            score = it.get("ai_score", 5)
            sentiment = it.get("ai_sentiment", "NEUTRAL")
            impact = it.get("ai_impact", "MEDIUM")
            relevance = it.get("relevance", 0)

            if sentiment == "BULLISH":
                sent_badge = "🟢 BULLISH"
            elif sentiment == "BEARISH":
                sent_badge = "🔴 BEARISH"
            else:
                sent_badge = "⚪ NEUTRAL"

            sectors = ", ".join(it.get("ai_sectors", [])) if it.get("ai_sectors") else "General"
            sectors = clean_table_text(sectors)
            reasoning = clean_table_text(it.get("ai_reasoning", ""))
            if len(reasoning) > 140:
                reasoning = reasoning[:140] + "..."
            time_str = clean_table_text(str(it.get("timestamp", ""))[:19])
            source = clean_table_text(it.get("source", ""))
            title = clean_table_text(it.get("title", ""))
            link = it.get("link", "#")

            other_srcs = it.get("other_sources", [])
            if len(other_srcs) > 1:
                alt_names = [clean_table_text(s.get("source", "")) for s in other_srcs if isinstance(s, dict) and s.get("source") != source]
                if alt_names:
                    source_display = f"{source} (+{len(alt_names)})"
                else:
                    source_display = source
            else:
                source_display = source

            safe_title = title.replace("[", "(").replace("]", ")")
            title_link = f"[{safe_title}]({link})" if link and link != "#" else safe_title

            if relevance >= 40 or score >= 7 or impact == "HIGH":
                top_rows.append([
                    f"{score}/10",
                    sent_badge,
                    impact,
                    title_link,
                    sectors,
                    reasoning,
                    source_display,
                    f"{relevance}%",
                    time_str
                ])
            else:
                bottom_link = f"[🔗 Open Wire ↗]({link})" if link and link != "#" else "—"
                bottom_rows.append([
                    time_str,
                    source_display,
                    title_link,
                    f"{relevance}%",
                    sent_badge,
                    bottom_link
                ])

        if not top_rows:
            top_rows.append(["-", "⚪ Live Stream", "-", "Awaiting incoming high-impact catalysts from global wires...", "-", "Feeds polling continuously...", "-", "-", "-"])

        if not bottom_rows:
            bottom_rows.append(["-", "-", "No general news items in cache", "-", "-", "-"])

        cal_status = "🟢 Connected" if telegram_notifier.is_calendar_configured() else "⚪ Standalone"
        status_str = (
            f"🟢 **System Engine:** `ONLINE` &nbsp;|&nbsp; "
            f"📰 **Cached News:** `{len(items)}` &nbsp;|&nbsp; "
            f"📅 **Multi-Market Events:** `{len(calendar_engine.events)}` &nbsp;|&nbsp; "
            f"📡 **Telegram Broadcast:** `{cal_status}` &nbsp;|&nbsp; "
            f"⏱️ **IST Clock:** `{now_ist().strftime('%H:%M:%S IST')}`"
        )
        news_visual_html = render_news_feed_html(items)
        return status_str, news_visual_html, top_rows, bottom_rows
    except Exception as e:
        status_err = f"🟢 **System Engine:** `ONLINE` | Refreshed: `{now_ist().strftime('%H:%M:%S IST')}`"
        empty_top = [["-", "-", "-", f"Feeds syncing: {str(e)}", "-", "-", "-", "-", "-"]]
        empty_bottom = [["-", "-", "-", "-", "-", "-"]]
        return status_err, f'<div class="epm-empty-state"><div class="epm-empty-icon">📡</div><div class="epm-empty-title">Connecting to Global Wire...</div><div class="epm-empty-sub">{str(e)}</div></div>', empty_top, empty_bottom


def get_calendar_tables(range_filter: str = "all", market_filter: str = "ALL"):
    try:
        events = calendar_engine.get_enriched_events(filter_range=range_filter, market_filter=market_filter)
        calendar_visual_html = render_calendar_feed_html(events)
        cal_rows = []
        for ev in events:
            mkt = ev.get("market", "NSE").upper()
            mkt_badge = MARKET_META.get(mkt, MARKET_META["NSE"])["badge"]
            impact = ev.get("impact", "HIGH")
            imp_badge = "🔥 HIGH" if impact == "HIGH" else ("⚡ MEDIUM" if impact == "MEDIUM" else "💤 LOW")
            linked_title = clean_table_text(ev.get("linked_news_title", ""))
            linked_url = ev.get("linked_news_url", "")
            if linked_title and linked_url:
                safe_linked = linked_title.replace("[", "(").replace("]", ")")
                short_title = safe_linked[:45] + "..." if len(safe_linked) > 45 else safe_linked
                linked_display = f"[🔗 {short_title}]({linked_url})"
            elif linked_title:
                short_title = linked_title[:45] + "..." if len(linked_title) > 45 else linked_title
                linked_display = f"🔗 {short_title}"
            else:
                gcal_url = google_calendar_manager.generate_one_click_url(ev)
                linked_display = f"[📅 +GCal]({gcal_url})"

            raw_ev_name = clean_table_text(ev.get("event", "Scheduled Release"))
            if len(raw_ev_name) > 110:
                raw_ev_name = raw_ev_name[:110] + "..."

            cal_rows.append([
                clean_table_text(ev.get("id", "")),
                mkt_badge,
                clean_table_text(ev.get("date", "")),
                f"{clean_table_text(ev.get('time', ''))} IST",
                clean_table_text(ev.get("timer", "")),
                clean_table_text(ev.get("symbol", "")),
                raw_ev_name,
                imp_badge,
                clean_table_text(ev.get("previous", "—")),
                clean_table_text(ev.get("forecast", "—")),
                clean_table_text(ev.get("actual", "⏳ Pending")),
                clean_table_text(ev.get("outcome_sentiment", "⏳ PENDING")),
                linked_display
            ])

        if not cal_rows:
            cal_rows.append(["-", "-", "-", "-", "-", "-", "No events for selected market/time filter", "-", "-", "-", "-", "-", "-"])

        holidays_data = calendar_engine.get_holiday_snapshot().get("comparison", [])
        hol_rows = []
        for h in holidays_data:
            hol_rows.append([
                clean_table_text(h.get("date", "")),
                clean_table_text(h.get("day", "")),
                clean_table_text(h.get("description", "")),
                clean_table_text(h.get("nse_status", "")),
                clean_table_text(h.get("bse_status", "")),
                clean_table_text(h.get("mcx_status", "")),
                clean_table_text(h.get("nyse_status", "")),
                clean_table_text(h.get("crypto_status", ""))
            ])

        if not hol_rows:
            hol_rows.append(["-", "-", "No upcoming holidays recorded", "-", "-", "-", "-", "-"])

        cal_summary = (
            f"📊 **Market:** `{market_filter}` &nbsp;|&nbsp; "
            f"⏳ **Filter Window:** `{range_filter.upper()}` &nbsp;|&nbsp; "
            f"📈 **Active Events:** `{len(events)}` &nbsp;|&nbsp; "
            f"⏱️ **IST Clock:** `{now_ist().strftime('%H:%M:%S IST')}` &nbsp;|&nbsp; "
            f"📅 **iCal Feed:** `/api/calendar/ics`"
        )
        return cal_summary, calendar_visual_html, cal_rows, hol_rows
    except Exception as e:
        err_sum = f"📅 **Market Calendar Status:** Active | `{now_ist().strftime('%Y-%m-%d %H:%M:%S IST')}`"
        empty_cal = [["-", "-", "-", "-", "-", "-", f"Calendar Notice: {str(e)}", "-", "-", "-", "-", "-", "-"]]
        empty_hol = [["-", "-", "-", "-", "-", "-", "-", "-"]]
        return err_sum, f'<div class="epm-empty-state"><div class="epm-empty-icon">📅</div><div class="epm-empty-title">Calendar Initializing</div><div class="epm-empty-sub">{str(e)}</div></div>', empty_cal, empty_hol


def sync_and_refresh_calendar(range_filter: str = "all", market_filter: str = "ALL"):
    try:
        calendar_engine.sync_all_calendars()
    except Exception as e:
        print(f"[Calendar] Sync error: {e}")
    return get_calendar_tables(range_filter, market_filter)


def push_today_photo_snapshot_all_markets():
    ok, msg = calendar_engine.dispatch_all_markets_today_photo_snapshot()
    if ok:
        return f"✅ **Today's Infographic Photo Cards dispatched as 5 separate market images (`NSE`, `BSE`, `MCX`, `CRYPTO`, `NYSE`) to `{telegram_notifier.calendar_chat_id}`!** ({msg})"
    return f"⚠️ **Could not send Today's Photo Cards:** {msg} *(Configure Calendar Telegram Chat ID in Tab 3)*"


def push_tomorrow_photo_snapshot_all_markets():
    ok, msg = calendar_engine.dispatch_all_markets_tomorrow_photo_snapshot()
    if ok:
        return f"✅ **Tomorrow's Infographic Photo Cards dispatched as 5 separate market images (`NSE`, `BSE`, `MCX`, `CRYPTO`, `NYSE`) to `{telegram_notifier.calendar_chat_id}`!** ({msg})"
    return f"⚠️ **Could not send Tomorrow's Photo Cards:** {msg} *(Configure Calendar Telegram Chat ID in Tab 3)*"


def push_today_snapshot_all_markets():
    ok, msg = calendar_engine.dispatch_all_markets_today_snapshot()
    if ok:
        return f"✅ **Today's Complete Calendar & Timer Snapshot sent as 5 separate text messages (`NSE`, `BSE`, `MCX`, `CRYPTO`, `NYSE`) to `{telegram_notifier.calendar_chat_id}`!** ({msg})"
    return f"⚠️ **Could not send Today's Snapshot:** {msg} *(Configure Calendar Telegram Chat ID in Tab 3)*"


def push_tomorrow_snapshot_all_markets():
    ok, msg = calendar_engine.dispatch_all_markets_tomorrow_snapshot()
    if ok:
        return f"✅ **Tomorrow's Lined-Up Events Snapshot sent as 5 separate text messages (`NSE`, `BSE`, `MCX`, `CRYPTO`, `NYSE`) to `{telegram_notifier.calendar_chat_id}`!** ({msg})"
    return f"⚠️ **Could not send Tomorrow's Snapshot:** {msg} *(Configure Calendar Telegram Chat ID in Tab 3)*"


def push_holiday_check_alert():
    ok, msg = calendar_engine.dispatch_next_day_holiday_alerts(force_preview=True)
    if ok:
        return f"✅ **Trading Holiday Alert dispatched separately per market to `{telegram_notifier.calendar_chat_id}`!** ({msg})"
    return f"ℹ️ **Holiday Check:** {msg}"


def handle_manual_event_save(
    evt_id: str,
    mkt_s: str,
    date_s: str,
    time_s: str,
    symbol_s: str,
    event_s: str,
    impact_s: str,
    prev_s: str,
    fore_s: str,
    actual_s: str,
    sent_s: str,
    forward_tg: bool,
    current_range: str,
    current_market: str
):
    ev = calendar_engine.update_or_add_event(
        event_id=evt_id,
        date_str=date_s,
        time_str=time_s,
        symbol=symbol_s,
        event_name=event_s,
        impact=impact_s,
        previous=prev_s,
        forecast=fore_s,
        actual=actual_s,
        sentiment=sent_s,
        market=mkt_s,
        forward_now=forward_tg
    )
    cal_summary, cal_visual_html, cal_rows, _ = get_calendar_tables(current_range, current_market)
    status_msg = f"✅ **Saved [{ev['market']}] Event `{ev['id']}` ({ev['event']}) — Outcome: `{ev['actual']}`.**"
    if forward_tg:
        status_msg += f" Dispatched individual `{ev['market']}` update to Calendar Telegram Channel!"
    return status_msg, cal_summary, cal_visual_html, cal_rows


def push_weekly_calendar_dispatch():
    ok, msg = calendar_engine.dispatch_weekly_calendar_message()
    if ok:
        return f"✅ **Complete 7-Day Weekly Calendar Link dispatched to `{telegram_notifier.calendar_chat_id}` with 1-click Google Calendar & Apple Calendar sync!**"
    return f"⚠️ **Could not send Weekly Calendar Link:** {msg} *(Configure Calendar Telegram Chat ID in Tab 3)*"


def save_admin_telegram_settings(
    news_token: str,
    news_chat: str,
    news_en: bool,
    cal_token: str,
    cal_chat: str,
    cal_en: bool,
    on_countdown: bool,
    on_outcome: bool,
    on_linked: bool,
    auto_today_7am: bool,
    auto_tom_705am: bool,
    auto_hol_7am: bool,
    send_photos: bool = True,
    public_url: str = "",
    auto_weekly_fri7am: bool = False,
    auto_circulars_tg: bool = False
):
    telegram_notifier.save_admin_settings(
        news_bot_token=news_token,
        news_chat_id=news_chat,
        news_enabled=news_en,
        calendar_bot_token=cal_token,
        calendar_chat_id=cal_chat,
        calendar_enabled=cal_en,
        alert_on_countdown=on_countdown,
        alert_on_outcome=on_outcome,
        alert_on_linked_news=on_linked,
        auto_daily_today_7am=auto_today_7am,
        auto_daily_tomorrow_705am=auto_tom_705am,
        auto_holiday_7am=auto_hol_7am,
        send_as_photos=send_photos,
        public_app_url=public_url,
        auto_weekly_fri_7am=auto_weekly_fri7am,
        auto_circulars_tg=auto_circulars_tg
    )
    format_mode = "Infographic Photo Cards 📸" if send_photos else "Detailed Text Messages 💬"
    return (
        f"✅ **Admin Telegram & Automated Schedule Settings Saved!**\n"
        f"- **News Channel ID:** `{telegram_notifier.chat_id or 'Not Set'}` (Enabled: `{telegram_notifier.enabled}`)\n"
        f"- **Calendar & Outcomes Channel ID:** `{telegram_notifier.calendar_chat_id or 'Not Set'}` (Enabled: `{telegram_notifier.calendar_enabled}`)\n"
        f"- **Public Portal URL:** `{telegram_notifier.get_public_url()}`\n"
        f"- **Morning Dispatch Format:** `{format_mode}`\n"
        f"- **Daily IST Automation:** 7:00 AM Today Snapshot=`{auto_today_7am}` | 7:05 AM Tomorrow Snapshot=`{auto_tom_705am}` | 7:00 AM Pre-Holiday Alert=`{auto_hol_7am}` | Friday 7:00 AM Weekly Link=`{auto_weekly_fri7am}` | Regulatory Circular Alerts=`{auto_circulars_tg}`"
    )


def trigger_sync_google_cal():
    events = calendar_engine.get_enriched_events(filter_range="all", market_filter="ALL")
    success, fail = google_calendar_manager.sync_events_batch(events)
    if google_calendar_manager.is_api_configured():
        return f"✅ **Synced {success} events to Google Calendar (`{google_calendar_manager.calendar_id}`) with 1-hr alarms!** (Failed: {fail})"
    return f"⚠️ **Google Calendar API not configured yet.** (Configured Calendar ID: `{google_calendar_manager.calendar_id or 'None'}`). Add Service Account credentials in Tab 3."


def save_google_calendar_settings(gcal_id: str, sa_json: str, sa_file: str, gcal_enabled: bool):
    google_calendar_manager.save_config(
        calendar_id=gcal_id,
        service_account_json_str=sa_json,
        service_account_file=sa_file,
        enabled=gcal_enabled
    )
    status_icon = "🟢 Connected" if google_calendar_manager.is_api_configured() else "⚠️ Credentials Needed"
    return f"✅ **Saved Google Calendar Settings!** Status: {status_icon} (Target ID: `{gcal_id}`)"


def trigger_test_telegram(target_channel: str):
    ok, detail = telegram_notifier.send_test_alert(channel_type=target_channel)
    if ok:
        return f"✅ **Test alert delivered to {target_channel.upper()} Telegram channel!**"
    return f"❌ **Test alert failed for {target_channel.upper()} channel:** {detail}"


def get_sources_table():
    try:
        rows = []
        for s in news_worker.sources:
            tg_status = "✅ Enabled" if s.get("forward_telegram", True) else "❌ Disabled"
            wa_status = "✅ Enabled" if s.get("forward_whatsapp", True) else "❌ Disabled"
            rows.append([
                s.get("name", ""),
                s.get("category", "General"),
                s.get("type", "RSS"),
                tg_status,
                wa_status,
                s.get("url", "")
            ])
        return rows
    except Exception as e:
        return [["-", "-", "-", "-", "-", f"Error loading sources: {str(e)}"]]


def manual_refresh():
    try:
        news_worker.poll_cycle()
        time.sleep(0.5)
    except Exception as e:
        print(f"[NewsWorker] Manual refresh error: {e}")
    return get_dashboard_tables()


def test_ai_rating(headline: str, summary: str):
    if not headline or not headline.strip():
        return "⚠️ **Input Required:** Please enter a breaking news headline to evaluate."
    try:
        res = ai_analyzer.analyze_news(headline.strip(), (summary or "").strip() or headline.strip(), "Manual Test")
        sent = res.get('sentiment', 'NEUTRAL')
        badge = "🟢 BULLISH" if sent == "BULLISH" else ("🔴 BEARISH" if sent == "BEARISH" else "⚪ NEUTRAL")
        return (
            f"**Impact Score:** `{res.get('score', 0)}/10`  |  **Sentiment:** {badge}  |  **Impact Level:** `{res.get('impact', 'MEDIUM')}`\n\n"
            f"**Affected Sectors / Tickers:** {', '.join(res.get('sectors', [])) or 'Broad Market'}\n\n"
            f"**Market Context & Rationale:** {res.get('reasoning', 'No rationale available.')}"
        )
    except Exception as e:
        return f"⚠️ **AI Evaluation Notice:** Could not score headline: {str(e)}"


def save_forwarding_rules(tg_selected: List[str], wa_selected: List[str], min_score: int):
    try:
        news_worker.save_config(tg_selected, wa_selected, min_score)
        updated_sources = get_sources_table()
        return f"✅ **Forwarding rules successfully updated!** ({len(tg_selected)} sources for Telegram, {len(wa_selected)} for WhatsApp, Min AI Score: {min_score})", updated_sources
    except Exception as e:
        return f"⚠️ **Error updating forwarding rules:** {str(e)}", get_sources_table()


all_source_names = [s["name"] for s in news_worker.sources]
default_tg_selected = [s["name"] for s in news_worker.sources if s.get("forward_telegram", True)]
default_wa_selected = [s["name"] for s in news_worker.sources if s.get("forward_whatsapp", True)]


# ─── Custom Responsive CSS (100% Full-Width Display, Zero Horizontal Scroll) ─

# ─── Clean Modern Financial Terminal (Crisp White Theme, Uniform Typography) ──


def render_table_ribbon(table_id: str, title: str, subtitle: str = "", count_badge: str = "") -> str:
    sub_badge = f'<span class="epm-ribbon-badge">{subtitle}</span>' if subtitle else ""
    cnt_badge = f'<span class="epm-ribbon-count" id="{table_id}_count">{count_badge}</span>' if count_badge else ""
    return f"""
    <div class="epm-table-ribbon" data-target="{table_id}">
        <div class="epm-ribbon-left">
            <span class="epm-ribbon-bullet">●</span>
            <span class="epm-ribbon-title">{title}</span>
            {sub_badge}
            {cnt_badge}
        </div>
        <div class="epm-ribbon-controls">
            <div class="epm-density-group" title="Adjust visible row density and line clamping">
                <span class="epm-control-label">Density:</span>
                <button type="button" class="epm-density-btn active" data-density="compact" onclick="window.epmSetDensity('{table_id}', 'compact', this)" title="Compact (2-Line Clamp)">Compact</button>
                <button type="button" class="epm-density-btn" data-density="standard" onclick="window.epmSetDensity('{table_id}', 'standard', this)" title="Standard (4-Line Clamp)">Standard</button>
                <button type="button" class="epm-density-btn" data-density="expanded" onclick="window.epmSetDensity('{table_id}', 'expanded', this)" title="Full Text (Unconstrained)">Expanded</button>
            </div>
            <button type="button" class="epm-ribbon-btn" onclick="window.epmExportCSV('{table_id}')" title="Download table records as standard RFC-4180 CSV">
                📥 <span>CSV</span>
            </button>
            <button type="button" class="epm-ribbon-btn" onclick="window.epmToggleFocus('{table_id}')" title="Full-Screen Focus Mode (Press ESC to exit)">
                ⛶ <span>Focus</span>
            </button>
            <button type="button" class="epm-ribbon-btn epm-collapse-btn" onclick="window.epmToggleCollapse('{table_id}', this)" title="Collapse or Expand this data table">
                <span>−</span>
            </button>
        </div>
    </div>
    """


CUSTOM_CSS = """
/* ═══════════════════════════════════════════════════════════════════════════
   EPM PRO INSTITUTIONAL FINANCIAL TERMINAL - ULTRA-PREMIUM 2026 WHITE THEME
   Inspired by: Bloomberg Terminal, TradingView, Linear, Vercel
   Design Principles:
   1. Pure white (#ffffff) canvas with subtle light slate (#f8fafc) elevations.
   2. Crisp, clean typography: Inter for UI/copy, JetBrains Mono for numbers/tickers.
   3. High density layout: zero wasted space, strict 2-line clamp on text.
   4. Micro-interactions: refined button states, crisp borders, subtle hover pills.
   ═══════════════════════════════════════════════════════════════════════════ */

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

:root {
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    
    --bg-page: #ffffff;
    --bg-surface: #ffffff;
    --bg-surface-elevated: #f8fafc;
    --bg-surface-subtle: #f1f5f9;
    
    --border-subtle: #f1f5f9;
    --border-color: #e2e8f0;
    --border-strong: #cbd5e1;
    --border-focus: #2563eb;
    
    --text-primary: #0f172a;
    --text-secondary: #334155;
    --text-muted: #64748b;
    
    --accent-blue: #2563eb;
    --accent-blue-hover: #1d4ed8;
    --accent-emerald: #059669;
    --accent-amber: #d97706;
    --accent-rose: #e11d48;
    
    --radius-xs: 4px;
    --radius-sm: 6px;
    --radius-md: 8px;
    --radius-lg: 12px;
}

/* 1. Global Reset & Pure White Baseline */
html, body {
    width: 100% !important;
    max-width: 100vw !important;
    overflow-x: hidden !important;
    margin: 0 !important;
    padding: 0 !important;
    background-color: #ffffff !important;
    color: var(--text-primary) !important;
    font-family: var(--font-sans) !important;
    font-size: 13px !important;
    line-height: 1.45 !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

*, *::before, *::after {
    box-sizing: border-box !important;
}

/* 2. Gradio Container (Enforced Light/White Institutional Layout) */
.gradio-container, 
.gradio-container > .main, 
.gradio-container > .wrap,
div[class*="gradio-container"],
.dark, .light {
    max-width: 100% !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 8px 20px !important;
    background-color: #ffffff !important;
    color: var(--text-primary) !important;
    overflow-x: hidden !important;
}

/* 3. Typography & Section Headers */
h1, h2, h3, h4 {
    font-family: var(--font-sans) !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.02em !important;
    margin-block: 0.4rem 0.5rem !important;
}

h1 {
    font-size: 20px !important;
    font-weight: 800 !important;
    color: #0f172a !important;
}

h2 {
    font-size: 16px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
}

h3 {
    font-size: 13px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    color: #334155 !important;
    margin-top: 10px !important;
    margin-bottom: 8px !important;
}

h4 {
    font-size: 12px !important;
    font-weight: 700 !important;
    color: #475569 !important;
}

/* 4. Complete Eradication of Gradio Tab Navigation Bar to prevent Duplicate Menus */
.tab-wrapper,
.tab-wrapper.svelte-11gaq1,
.tab-container,
.tab-container.svelte-11gaq1,
div[role="tablist"],
.gradio-container div[role="tablist"],
.tabs > .tab-wrapper,
.gradio-container .tab-wrapper,
.tab-nav,
.tabs > .tab-nav,
div[data-testid="tabs"] > .tab-nav,
.gradio-container .tab-nav {
    height: 0px !important;
    max-height: 0px !important;
    min-height: 0px !important;
    padding: 0 !important;
    margin: 0 !important;
    overflow: hidden !important;
    opacity: 0 !important;
    pointer-events: none !important;
    border: none !important;
    visibility: hidden !important;
    line-height: 0 !important;
    font-size: 0 !important;
}

.tab-container:after,
.tab-wrapper:after {
    display: none !important;
    height: 0 !important;
    border: none !important;
}

/* 5. Streamlined Action Buttons (Compact, Uniform Heights, No Clutter) */
button, .gr-button {
    font-family: var(--font-sans) !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    border-radius: var(--radius-sm) !important;
    padding: 6px 12px !important;
    min-height: 33px !important;
    height: 33px !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    transition: all 0.15s ease !important;
    white-space: nowrap !important;
    text-overflow: ellipsis !important;
}

button.primary, .gr-button-primary {
    background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
    color: #ffffff !important;
    border: 1px solid #1d4ed8 !important;
    box-shadow: 0 1px 2px rgba(37, 99, 235, 0.2) !important;
}

button.primary:hover, .gr-button-primary:hover {
    background: linear-gradient(135deg, #1d4ed8, #1e40af) !important;
    box-shadow: 0 2px 4px rgba(37, 99, 235, 0.3) !important;
    transform: translateY(-1px);
}

button.secondary, .gr-button-secondary {
    background: #ffffff !important;
    color: #334155 !important;
    border: 1px solid #cbd5e1 !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02) !important;
}

button.secondary:hover, .gr-button-secondary:hover {
    background: #f8fafc !important;
    border-color: #94a3b8 !important;
    color: #0f172a !important;
}

/* 6. Form Controls, Radios & Inputs */
input, textarea, select {
    background-color: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    color: #0f172a !important;
    border-radius: var(--radius-sm) !important;
    font-family: var(--font-sans) !important;
    font-size: 12.5px !important;
    padding: 6px 10px !important;
}

input:focus, textarea:focus, select:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 1px #2563eb !important;
    outline: none !important;
}

.gr-radio, fieldset {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: var(--radius-sm) !important;
    padding: 4px 10px !important;
}

.gr-radio label, fieldset label {
    font-size: 12px !important;
    font-weight: 500 !important;
    color: #334155 !important;
}

/* 7. Accordions (Sleek Micro-Borders) */
.gr-accordion {
    border: 1px solid #e2e8f0 !important;
    border-radius: var(--radius-md) !important;
    background: #ffffff !important;
    margin-top: 10px !important;
    margin-bottom: 12px !important;
    overflow: hidden !important;
}

.gr-accordion > .label-wrap {
    background: #f8fafc !important;
    padding: 8px 12px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    color: #334155 !important;
    border-bottom: 1px solid #e2e8f0 !important;
}

.gr-accordion > .label-wrap:hover {
    background: #f1f5f9 !important;
    color: #0f172a !important;
}

/* 8. Institutional High-Density Data Tables */
.table-wrap,
.gradio-dataframe,
div[data-testid="dataframe"],
.table-container {
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: auto !important;
    border-radius: var(--radius-md) !important;
    border: 1px solid #e2e8f0 !important;
    background: #ffffff !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02) !important;
    margin-bottom: 12px !important;
}

table {
    table-layout: fixed !important;
    width: 100% !important;
    max-width: 100% !important;
    border-collapse: collapse !important;
    font-family: var(--font-sans) !important;
    background: #ffffff !important;
}

thead th {
    background-color: #f8fafc !important;
    color: #475569 !important;
    font-family: var(--font-sans) !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    padding: 7px 8px !important;
    border-bottom: 1.5px solid #cbd5e1 !important;
    border-right: 1px solid #f1f5f9 !important;
    white-space: normal !important;
    vertical-align: middle !important;
    position: sticky !important;
    top: 0 !important;
    z-index: 2 !important;
}

tbody td {
    padding: 5px 8px !important;
    font-size: 12px !important;
    color: #0f172a !important;
    border-bottom: 1px solid #f1f5f9 !important;
    border-right: 1px solid #f8fafc !important;
    vertical-align: middle !important;
    line-height: 1.35 !important;
    word-break: break-word !important;
    overflow-wrap: anywhere !important;
    background: #ffffff !important;
    height: auto !important;
}

tbody tr:nth-child(even) td {
    background-color: #fcfdfe !important;
}

tbody tr:hover td {
    background-color: #f0f7ff !important;
}

/* 9. Monospace Elements for Numbers, Dates, Timers */
code, .timer-cell, pre {
    font-family: var(--font-mono) !important;
    font-size: 11px !important;
    background: #f1f5f9 !important;
    color: #0f172a !important;
    padding: 2px 5px !important;
    border-radius: 4px !important;
    border: 1px solid #e2e8f0 !important;
}

/* 10. Strict 2-Line Clamp for Headlines, Events, Summaries */
#top_news_table tbody td:nth-child(4) > *,
#top_news_table tbody td:nth-child(4) a,
#top_news_table tbody td:nth-child(5) > *,
#top_news_table tbody td:nth-child(6) > *,
#bottom_news_table tbody td:nth-child(3) > *,
#bottom_news_table tbody td:nth-child(3) a,
#calendar_table tbody td:nth-child(7) > *,
#calendar_table tbody td:nth-child(13) > *,
#calendar_table tbody td:nth-child(13) a,
#circ_table tbody td:nth-child(5) > *,
#circ_table tbody td:nth-child(5) a,
#circ_table tbody td:nth-child(7) > * {
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    max-height: 2.7em !important;
    line-height: 1.35 !important;
    word-break: break-word !important;
}

#top_news_table tbody td:nth-child(4),
#top_news_table tbody td:nth-child(5),
#top_news_table tbody td:nth-child(6),
#bottom_news_table tbody td:nth-child(3),
#calendar_table tbody td:nth-child(7),
#calendar_table tbody td:nth-child(13),
#circ_table tbody td:nth-child(5),
#circ_table tbody td:nth-child(7) {
    max-height: 3.1em !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    line-height: 1.35 !important;
}

/* 11. Column Allocations for Tables */

/* Top News Table */
#top_news_table th:nth-child(1), #top_news_table td:nth-child(1) { width: 5.5% !important; text-align: center !important; font-family: var(--font-mono) !important; font-weight: 700 !important; color: #b45309 !important; }
#top_news_table th:nth-child(2), #top_news_table td:nth-child(2) { width: 8.5% !important; text-align: center !important; font-weight: 600 !important; }
#top_news_table th:nth-child(3), #top_news_table td:nth-child(3) { width: 7% !important; text-align: center !important; font-weight: 700 !important; }
#top_news_table th:nth-child(4), #top_news_table td:nth-child(4) { width: 32% !important; font-weight: 600 !important; color: #0f172a !important; }
#top_news_table th:nth-child(5), #top_news_table td:nth-child(5) { width: 11% !important; color: #475569 !important; font-size: 11.5px !important; }
#top_news_table th:nth-child(6), #top_news_table td:nth-child(6) { width: 20% !important; color: #334155 !important; font-style: italic !important; font-size: 11.5px !important; }
#top_news_table th:nth-child(7), #top_news_table td:nth-child(7) { width: 7% !important; font-size: 11px !important; color: #0284c7 !important; font-weight: 600 !important; }
#top_news_table th:nth-child(8), #top_news_table td:nth-child(8) { width: 4% !important; text-align: center !important; font-family: var(--font-mono) !important; color: #475569 !important; }
#top_news_table th:nth-child(9), #top_news_table td:nth-child(9) { width: 5% !important; text-align: center !important; font-family: var(--font-mono) !important; font-size: 11px !important; color: #64748b !important; }

/* Bottom News Table */
#bottom_news_table th:nth-child(1), #bottom_news_table td:nth-child(1) { width: 8% !important; text-align: center !important; font-family: var(--font-mono) !important; font-size: 11px !important; color: #64748b !important; }
#bottom_news_table th:nth-child(2), #bottom_news_table td:nth-child(2) { width: 12% !important; color: #0284c7 !important; font-weight: 600 !important; }
#bottom_news_table th:nth-child(3), #bottom_news_table td:nth-child(3) { width: 56% !important; font-weight: 500 !important; color: #0f172a !important; }
#bottom_news_table th:nth-child(4), #bottom_news_table td:nth-child(4) { width: 6% !important; text-align: center !important; font-family: var(--font-mono) !important; color: #475569 !important; }
#bottom_news_table th:nth-child(5), #bottom_news_table td:nth-child(5) { width: 8% !important; text-align: center !important; }
#bottom_news_table th:nth-child(6), #bottom_news_table td:nth-child(6) { width: 10% !important; text-align: center !important; font-size: 11px !important; color: #2563eb !important; }

/* Calendar Table */
#calendar_table th:nth-child(1), #calendar_table td:nth-child(1) { width: 6.5% !important; font-family: var(--font-mono) !important; font-size: 10.5px !important; color: #64748b !important; text-align: center !important; }
#calendar_table th:nth-child(2), #calendar_table td:nth-child(2) { width: 5% !important; text-align: center !important; font-weight: 600 !important; }
#calendar_table th:nth-child(3), #calendar_table td:nth-child(3) { width: 6% !important; text-align: center !important; font-family: var(--font-mono) !important; font-size: 11px !important; }
#calendar_table th:nth-child(4), #calendar_table td:nth-child(4) { width: 5.5% !important; text-align: center !important; font-family: var(--font-mono) !important; font-weight: 700 !important; color: #0284c7 !important; }
#calendar_table th:nth-child(5), #calendar_table td:nth-child(5) { width: 7.5% !important; text-align: center !important; font-family: var(--font-mono) !important; font-weight: 700 !important; color: #d97706 !important; }
#calendar_table th:nth-child(6), #calendar_table td:nth-child(6) { width: 8.5% !important; font-weight: 700 !important; color: #0f172a !important; font-family: var(--font-mono) !important; }
#calendar_table th:nth-child(7), #calendar_table td:nth-child(7) { width: 22% !important; font-weight: 600 !important; color: #0f172a !important; }
#calendar_table th:nth-child(8), #calendar_table td:nth-child(8) { width: 6% !important; text-align: center !important; font-weight: 700 !important; }
#calendar_table th:nth-child(9), #calendar_table td:nth-child(9) { width: 6% !important; text-align: right !important; font-family: var(--font-mono) !important; color: #475569 !important; }
#calendar_table th:nth-child(10), #calendar_table td:nth-child(10) { width: 6% !important; text-align: right !important; font-family: var(--font-mono) !important; color: #475569 !important; }
#calendar_table th:nth-child(11), #calendar_table td:nth-child(11) { width: 7.5% !important; text-align: right !important; font-family: var(--font-mono) !important; font-weight: 700 !important; color: #059669 !important; }
#calendar_table th:nth-child(12), #calendar_table td:nth-child(12) { width: 6% !important; text-align: center !important; font-weight: 600 !important; }
#calendar_table th:nth-child(13), #calendar_table td:nth-child(13) { width: 7.5% !important; text-align: center !important; font-size: 11px !important; color: #2563eb !important; }

/* Holidays Table */
#holidays_table th:nth-child(1), #holidays_table td:nth-child(1) { width: 8% !important; text-align: center !important; font-family: var(--font-mono) !important; }
#holidays_table th:nth-child(2), #holidays_table td:nth-child(2) { width: 7% !important; text-align: center !important; }
#holidays_table th:nth-child(3), #holidays_table td:nth-child(3) { width: 23% !important; font-weight: 600 !important; color: #0f172a !important; }
#holidays_table th:nth-child(4), #holidays_table td:nth-child(4) { width: 12% !important; text-align: center !important; }
#holidays_table th:nth-child(5), #holidays_table td:nth-child(5) { width: 12% !important; text-align: center !important; }
#holidays_table th:nth-child(6), #holidays_table td:nth-child(6) { width: 15% !important; text-align: center !important; }
#holidays_table th:nth-child(7), #holidays_table td:nth-child(7) { width: 13% !important; text-align: center !important; }
#holidays_table th:nth-child(8), #holidays_table td:nth-child(8) { width: 10% !important; text-align: center !important; }

/* Regulatory Circulars Table */
#circ_table th:nth-child(1), #circ_table td:nth-child(1) { width: 6% !important; text-align: center !important; font-weight: 700 !important; }
#circ_table th:nth-child(2), #circ_table td:nth-child(2) { width: 9% !important; font-family: var(--font-mono) !important; font-size: 11px !important; color: #0f172a !important; font-weight: 600 !important; text-align: center !important; }
#circ_table th:nth-child(3), #circ_table td:nth-child(3) { width: 6% !important; text-align: center !important; font-family: var(--font-mono) !important; color: #475569 !important; font-size: 11px !important; }
#circ_table th:nth-child(4), #circ_table td:nth-child(4) { width: 6% !important; text-align: center !important; font-weight: 700 !important; }
#circ_table th:nth-child(5), #circ_table td:nth-child(5) { width: 28% !important; font-weight: 600 !important; color: #0f172a !important; line-height: 1.35 !important; }
#circ_table th:nth-child(6), #circ_table td:nth-child(6) { width: 9% !important; color: #475569 !important; font-size: 11.5px !important; }
#circ_table th:nth-child(7), #circ_table td:nth-child(7) { width: 27% !important; color: #334155 !important; font-size: 11.5px !important; line-height: 1.35 !important; }
#circ_table th:nth-child(8), #circ_table td:nth-child(8) { width: 9% !important; text-align: center !important; }
#circ_table td:nth-child(8) a {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 3px 8px !important;
    background: #2563eb !important;
    color: #ffffff !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
    font-size: 11px !important;
    text-decoration: none !important;
    transition: all 0.15s ease !important;
    white-space: nowrap !important;
}
#circ_table td:nth-child(8) a:hover {
    background: #1d4ed8 !important;
    transform: translateY(-1px) !important;
}

/* Hyperlinks inside data tables */
#top_news_table td:nth-child(4) a,
#bottom_news_table td:nth-child(3) a,
#circ_table td:nth-child(5) a {
    color: #0f172a !important;
    font-weight: 600 !important;
    text-decoration: none !important;
    transition: color 0.15s ease !important;
}
#top_news_table td:nth-child(4) a:hover,
#bottom_news_table td:nth-child(3) a:hover,
#circ_table td:nth-child(5) a:hover {
    color: #2563eb !important;
    text-decoration: underline !important;
}
#bottom_news_table td:nth-child(6) a,
#calendar_table td:nth-child(13) a {
    color: #2563eb !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-decoration: none !important;
}
#bottom_news_table td:nth-child(6) a:hover,
#calendar_table td:nth-child(13) a:hover {
    text-decoration: underline !important;
}

/* 12. Visual Card Feed Components (Inside Accordions) */
.epm-stream-container {
    display: flex;
    flex-direction: column;
    gap: 10px;
    width: 100% !important;
    margin: 8px 0 16px 0;
}

.epm-card {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    padding: 12px 16px !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease !important;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.epm-card:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06) !important;
    border-color: #cbd5e1 !important;
}

.epm-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    padding-bottom: 6px;
    border-bottom: 1px solid #f1f5f9;
}

.epm-meta-left, .epm-meta-right {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
}

.epm-source-chip {
    font-family: var(--font-sans) !important;
    font-size: 10.5px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    background: #f1f5f9 !important;
    color: #1e293b !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    border: 1px solid #e2e8f0 !important;
}

.epm-time-chip {
    font-family: var(--font-mono) !important;
    font-size: 10.5px !important;
    color: #64748b !important;
}

.epm-score-pill {
    font-family: var(--font-mono) !important;
    font-size: 11.5px !important;
    font-weight: 700 !important;
    background: #0f172a !important;
    color: #38bdf8 !important;
    padding: 2px 8px !important;
    border-radius: 4px !important;
}

.epm-badge {
    font-family: var(--font-sans) !important;
    font-size: 10.5px !important;
    font-weight: 700 !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    display: inline-flex;
    align-items: center;
    gap: 3px;
}

.epm-badge.impact-high { background: #fff1f2 !important; color: #e11d48 !important; border: 1px solid #fecdd3 !important; }
.epm-badge.impact-medium { background: #f0f9ff !important; color: #0284c7 !important; border: 1px solid #bae6fd !important; }
.epm-badge.impact-low { background: #f8fafc !important; color: #64748b !important; border: 1px solid #e2e8f0 !important; }
.epm-badge.sent-bullish { background: #f0fdf4 !important; color: #16a34a !important; border: 1px solid #bbf7d0 !important; }
.epm-badge.sent-bearish { background: #fef2f2 !important; color: #dc2626 !important; border: 1px solid #fecaca !important; }
.epm-badge.sent-neutral { background: #f8fafc !important; color: #475569 !important; border: 1px solid #e2e8f0 !important; }
.epm-badge.sent-pending { background: #fffbeb !important; color: #b45309 !important; border: 1px solid #fde68a !important; }

.epm-news-title {
    font-family: var(--font-sans) !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
    text-decoration: none !important;
    line-height: 1.4 !important;
    transition: color 0.15s ease !important;
}
.epm-news-title:hover { color: #2563eb !important; }

.epm-news-reasoning {
    font-family: var(--font-sans) !important;
    font-size: 12.5px !important;
    color: #475569 !important;
    background: #f8fafc !important;
    padding: 6px 10px !important;
    border-radius: 6px !important;
    border-left: 3px solid #cbd5e1 !important;
    margin-top: 5px !important;
    line-height: 1.45 !important;
}

.epm-card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px !important;
    color: #64748b !important;
    padding-top: 4px;
}

.epm-sectors-wrap { display: flex; gap: 4px; flex-wrap: wrap; }
.epm-sector-tag {
    background: #f1f5f9 !important;
    color: #334155 !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-size: 10px !important;
    font-weight: 600 !important;
}

.epm-empty-state {
    background: #ffffff !important;
    border: 1px dashed #cbd5e1 !important;
    border-radius: 8px !important;
    padding: 30px 16px !important;
    text-align: center !important;
    color: #64748b !important;
    margin: 10px 0 !important;
}
.epm-empty-icon { font-size: 28px !important; margin-bottom: 6px; }
.epm-empty-title { font-size: 14px !important; font-weight: 700 !important; color: #0f172a !important; margin-bottom: 2px; }
.epm-empty-sub { font-size: 12px !important; color: #64748b !important; }

/* Calendar & Circulars Cards inside accordions */
.epm-cal-card, .epm-circ-card {
    border-left: 3px solid #2563eb !important;
}
.epm-mkt-chip, .epm-reg-chip {
    font-family: var(--font-sans) !important;
    font-weight: 700 !important;
    font-size: 10.5px !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    background: #f1f5f9 !important;
    border: 1px solid #cbd5e1 !important;
}
.epm-time-ist {
    font-family: var(--font-mono) !important;
    font-size: 11.5px !important;
    color: #0f172a !important;
}
.epm-timer-pill {
    font-family: var(--font-mono) !important;
    font-size: 10.5px !important;
    font-weight: 700 !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
}
.timer-active { background: #fff7ed !important; color: #c2410c !important; border: 1px solid #ffedd5 !important; }
.timer-live { background: #ecfdf5 !important; color: #047857 !important; border: 1px solid #a7f3d0 !important; }
.timer-done { background: #f8fafc !important; color: #64748b !important; border: 1px solid #e2e8f0 !important; }

.epm-gcal-btn {
    font-family: var(--font-sans) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    background: #f8fafc !important;
    color: #1d4ed8 !important;
    border: 1px solid #bfdbfe !important;
    padding: 4px 10px !important;
    border-radius: 4px !important;
    text-decoration: none !important;
    transition: all 0.15s ease !important;
}
.epm-gcal-btn:hover { background: #eff6ff !important; color: #1e40af !important; }

.epm-metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    gap: 6px;
    margin-top: 8px;
}
.epm-metric-box {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
    padding: 5px 8px !important;
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.epm-m-label {
    font-size: 9px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    color: #64748b !important;
}
.epm-m-val {
    font-family: var(--font-mono) !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
}

.epm-circ-bullets-box {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
    padding: 8px 12px !important;
    margin-top: 6px !important;
}
.epm-circ-bullets-head {
    font-size: 10.5px !important;
    color: #2563eb !important;
    text-transform: uppercase !important;
    font-weight: 700 !important;
    margin-bottom: 4px !important;
}
.epm-circ-bullets-list {
    margin: 0 !important;
    padding-left: 16px !important;
    font-size: 12px !important;
    color: #334155 !important;
    line-height: 1.45 !important;
}

/* 13. Dedicated User Guide & Operations Manual Styling */
.guide-container {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 4px 0 20px 0;
}
.guide-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 16px 20px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}
.guide-card h3 {
    font-size: 14px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
    margin-top: 0 !important;
    margin-bottom: 6px !important;
    display: flex;
    align-items: center;
    gap: 6px;
}
.guide-badge {
    font-family: var(--font-mono);
    font-size: 10.5px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    background: #eff6ff;
    color: #2563eb;
    border: 1px solid #dbeafe;
}
.guide-list {
    margin: 6px 0;
    padding-left: 18px;
    color: #334155;
    line-height: 1.55;
    font-size: 12.5px;
}
.guide-list li {
    margin-bottom: 5px;
}
.guide-pill {
    display: inline-block;
    padding: 1px 5px;
    background: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 11px;
    color: #0f172a;
    font-weight: 600;
}

/* 14. Top Institutional Sticky Telemetry Ribbon & Navbar */
.epm-top-navbar {
    position: sticky !important;
    top: 0 !important;
    z-index: 1000 !important;
    background: #ffffff !important;
    border-bottom: 1px solid #e2e8f0 !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04) !important;
    margin: -8px -20px 4px -20px !important;
    padding: 3px 14px 4px 14px !important;
}

/* Row 1: Brand Cluster, Live Telemetry & Macro Ticker Strip */
.epm-nav-row-1 {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 10px !important;
    flex-wrap: nowrap !important;
    height: 26px !important;
    line-height: 26px !important;
    overflow: hidden !important;
}

.epm-nav-brand-cluster {
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
    flex-shrink: 0 !important;
}

.epm-nav-logo {
    font-size: 15px !important;
}

.epm-nav-title {
    font-family: var(--font-sans) !important;
    font-size: 13.5px !important;
    font-weight: 800 !important;
    color: #0f172a !important;
    letter-spacing: -0.02em !important;
}

.epm-nav-version {
    font-family: var(--font-mono) !important;
    font-size: 9px !important;
    font-weight: 700 !important;
    color: #2563eb !important;
    background: #eff6ff !important;
    border: 1px solid #bfdbfe !important;
    padding: 0 4px !important;
    border-radius: 3px !important;
    height: 16px !important;
    line-height: 14px !important;
}

.epm-nav-status-badge {
    display: inline-flex !important;
    align-items: center !important;
    gap: 4px !important;
    padding: 0 5px !important;
    height: 16px !important;
    line-height: 14px !important;
    background: #f0fdf4 !important;
    border: 1px solid #bbf7d0 !important;
    border-radius: 3px !important;
    font-family: var(--font-mono) !important;
    font-size: 9px !important;
    font-weight: 700 !important;
    color: #16a34a !important;
}

.epm-live-dot {
    width: 6px !important;
    height: 6px !important;
    border-radius: 50% !important;
    background: #16a34a !important;
    display: inline-block !important;
    box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.2) !important;
    animation: epmPulse 2s infinite !important;
}

@keyframes epmPulse {
    0% { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.4); }
    70% { box-shadow: 0 0 0 5px rgba(22, 163, 74, 0); }
    100% { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0); }
}

.epm-nav-telemetry {
    display: inline-flex !important;
    align-items: center !important;
    gap: 4px !important;
    margin-left: 4px !important;
}

.epm-telem-pill {
    display: inline-flex !important;
    align-items: center !important;
    gap: 2px !important;
    height: 18px !important;
    line-height: 16px !important;
    padding: 0 5px !important;
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 3px !important;
    font-family: var(--font-mono) !important;
    font-size: 9.5px !important;
    color: #475569 !important;
    white-space: nowrap !important;
}

.epm-telem-pill b {
    color: #0f172a !important;
    font-weight: 700 !important;
}

.epm-telem-online {
    background: #f0fdf4 !important;
    border-color: #bbf7d0 !important;
    color: #16a34a !important;
    font-weight: 700 !important;
}

/* Macro Telemetry Strip */
.epm-telemetry-strip {
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
    overflow-x: auto !important;
    scrollbar-width: none !important;
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 4px !important;
    padding: 0 8px !important;
    height: 20px !important;
    line-height: 18px !important;
    flex: 0 1 auto !important;
}

.epm-telemetry-strip::-webkit-scrollbar {
    display: none !important;
}

.epm-ticker-item {
    display: flex !important;
    align-items: center !important;
    gap: 4px !important;
    font-family: var(--font-mono) !important;
    font-size: 10px !important;
    white-space: nowrap !important;
    cursor: default !important;
}

.epm-ticker-sym {
    font-weight: 700 !important;
    color: #475569 !important;
    font-size: 9.5px !important;
}

.epm-ticker-val {
    font-weight: 700 !important;
    color: #0f172a !important;
}

.epm-ticker-chg.up {
    font-weight: 700 !important;
    color: #16a34a !important;
    background: #f0fdf4 !important;
    border: 1px solid #bbf7d0 !important;
    padding: 0 3px !important;
    border-radius: 2px !important;
    font-size: 9px !important;
}

.epm-ticker-chg.down {
    font-weight: 700 !important;
    color: #dc2626 !important;
    background: #fef2f2 !important;
    border: 1px solid #fecaca !important;
    padding: 0 3px !important;
    border-radius: 2px !important;
    font-size: 9px !important;
}

.epm-ticker-divider {
    width: 1px !important;
    height: 10px !important;
    background: #cbd5e1 !important;
}

/* Row 2: Unified Navigation Tabs + Controls on ONE line */
.epm-nav-row-2 {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 8px !important;
    flex-wrap: nowrap !important;
    padding-top: 3px !important;
    margin-top: 3px !important;
    border-top: 1px solid #f1f5f9 !important;
    height: 27px !important;
    line-height: 27px !important;
}

.epm-quick-tabs-container {
    display: flex !important;
    gap: 4px !important;
    align-items: center !important;
    flex-wrap: nowrap !important;
}

.epm-tab-pill {
    display: inline-flex !important;
    align-items: center !important;
    gap: 4px !important;
    height: 23px !important;
    padding: 0 8px !important;
    font-family: var(--font-sans) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    border-radius: 12px !important;
    border: 1px solid #e2e8f0 !important;
    background: #ffffff !important;
    color: #475569 !important;
    cursor: pointer !important;
    transition: all 0.12s ease !important;
    white-space: nowrap !important;
}

.epm-tab-pill:hover {
    background: #f8fafc !important;
    color: #0f172a !important;
    border-color: #cbd5e1 !important;
}

.epm-tab-pill.active {
    background: #ffffff !important;
    color: #1d4ed8 !important;
    border: 1.5px solid #2563eb !important;
    box-shadow: 0 1px 3px rgba(37, 99, 235, 0.12), 0 0 0 2px rgba(37, 99, 235, 0.16) !important;
    font-weight: 700 !important;
}

.epm-tab-pill.active *,
.epm-tab-pill.active span,
.epm-tab-pill.active .epm-tab-pill-icon {
    color: #1d4ed8 !important;
    font-weight: 700 !important;
}

.epm-tab-pill.active:hover {
    background: #f8faff !important;
    border-color: #1d4ed8 !important;
}

/* Top Nav Controls Right */
.epm-nav-controls {
    display: flex !important;
    align-items: center !important;
    gap: 4px !important;
    flex-shrink: 0 !important;
    flex-wrap: nowrap !important;
}

.epm-nav-search-wrap {
    position: relative !important;
    display: flex !important;
    align-items: center !important;
}

#epm-watchlist-input {
    width: 120px !important;
    height: 23px !important;
    font-size: 10.5px !important;
    padding: 1px 18px 1px 18px !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 4px !important;
    background: #ffffff !important;
    color: #0f172a !important;
    transition: width 0.2s ease, border-color 0.15s ease !important;
}

#epm-watchlist-input:focus {
    width: 160px !important;
    border-color: #2563eb !important;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12) !important;
    outline: none !important;
}

.epm-nav-search-icon {
    position: absolute !important;
    left: 5px !important;
    font-size: 10px !important;
    pointer-events: none !important;
    color: #94a3b8 !important;
}

.epm-watchlist-clear-btn {
    position: absolute !important;
    right: 5px !important;
    background: transparent !important;
    border: none !important;
    font-size: 9px !important;
    color: #94a3b8 !important;
    cursor: pointer !important;
    padding: 0 !important;
}

.epm-watchlist-clear-btn:hover {
    color: #0f172a !important;
}

.epm-watchlist-badge {
    position: absolute !important;
    right: 18px !important;
    font-family: var(--font-mono) !important;
    font-size: 8.5px !important;
    background: #2563eb !important;
    color: #ffffff !important;
    padding: 0 3px !important;
    border-radius: 2px !important;
    font-weight: 700 !important;
    white-space: nowrap !important;
}

.epm-top-btn {
    display: inline-flex !important;
    align-items: center !important;
    gap: 3px !important;
    height: 23px !important;
    padding: 0 6px !important;
    font-family: var(--font-sans) !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    border-radius: 4px !important;
    border: 1px solid #cbd5e1 !important;
    background: #ffffff !important;
    color: #334155 !important;
    cursor: pointer !important;
    transition: all 0.12s ease !important;
    white-space: nowrap !important;
}

.epm-top-btn:hover {
    background: #f8fafc !important;
    border-color: #94a3b8 !important;
    color: #0f172a !important;
}

.epm-btn-active {
    background: #f0fdf4 !important;
    border-color: #86efac !important;
    color: #16a34a !important;
}

.epm-btn-muted {
    background: #fef2f2 !important;
    border-color: #fca5a5 !important;
    color: #dc2626 !important;
}

.epm-cmd-btn {
    background: #0f172a !important;
    color: #ffffff !important;
    border-color: #0f172a !important;
}

.epm-cmd-btn:hover {
    background: #1e293b !important;
    border-color: #1e293b !important;
    color: #ffffff !important;
}

.epm-kbd-badge {
    font-family: var(--font-mono) !important;
    font-size: 9px !important;
    background: #334155 !important;
    color: #38bdf8 !important;
    padding: 0 3px !important;
    border-radius: 2px !important;
    font-weight: 700 !important;
}

.epm-nav-link {
    font-family: var(--font-sans) !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    color: #2563eb !important;
    text-decoration: none !important;
    padding: 1px 6px !important;
    height: 23px !important;
    line-height: 19px !important;
    box-sizing: border-box !important;
    border-radius: 4px !important;
    background: #eff6ff !important;
    border: 1px solid #dbeafe !important;
    transition: all 0.12s ease !important;
    white-space: nowrap !important;
}

.epm-nav-link:hover {
    background: #dbeafe !important;
    color: #1d4ed8 !important;
}

/* 15. Hidden Telemetry Elements & Zero-Height Subheaders */
#epm-status-box, #cal_info_bar, #circ_info_bar, #cal_action_msg:empty, #circ_action_msg:empty {
    display: none !important;
    height: 0 !important;
    max-height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    overflow: hidden !important;
}

/* 16. Action Drawers (Zen Mode Smooth CSS Animation) */
.epm-action-drawer {
    transition: max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s ease, margin 0.3s ease, padding 0.3s ease !important;
    max-height: 500px !important;
    opacity: 1 !important;
    overflow: visible !important;
}

.epm-action-drawer.collapsed {
    max-height: 0 !important;
    height: 0 !important;
    opacity: 0 !important;
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    margin-top: 0 !important;
    margin-bottom: 0 !important;
    overflow: hidden !important;
    pointer-events: none !important;
    border: none !important;
    display: none !important;
}

.epm-drawer-toggle-row {
    margin-bottom: 4px !important;
}

#cal_drawer_toggle, #circ_drawer_toggle {
    font-family: var(--font-sans) !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    border-radius: 4px !important;
    margin: 0 !important;
    height: 24px !important;
    min-height: 24px !important;
    padding: 0 8px !important;
    background: #f8fafc !important;
    border: 1px dashed #cbd5e1 !important;
    color: #334155 !important;
    cursor: pointer !important;
    transition: all 0.15s ease !important;
    white-space: nowrap !important;
    flex-shrink: 0 !important;
}

#cal_drawer_toggle:hover, #circ_drawer_toggle:hover {
    background: #f1f5f9 !important;
    border-color: #94a3b8 !important;
    color: #0f172a !important;
}

/* 17. Table Header Ribbons & Multi-Density Engine */
.epm-table-ribbon {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-bottom: none !important;
    border-radius: 4px 4px 0 0 !important;
    padding: 2px 8px !important;
    margin-top: 4px !important;
    margin-bottom: 0 !important;
    min-height: 28px !important;
    height: 28px !important;
    gap: 6px !important;
    flex-wrap: nowrap !important;
}

.epm-ribbon-left {
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
    flex-wrap: nowrap !important;
}

.epm-ribbon-bullet {
    color: #2563eb !important;
    font-size: 9px !important;
}

.epm-ribbon-title {
    font-family: var(--font-sans) !important;
    font-size: 11.5px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
    text-transform: uppercase !important;
    letter-spacing: 0.03em !important;
}

.epm-ribbon-badge {
    font-family: var(--font-sans) !important;
    font-size: 9.5px !important;
    font-weight: 600 !important;
    color: #2563eb !important;
    background: #eff6ff !important;
    border: 1px solid #bfdbfe !important;
    padding: 0 5px !important;
    border-radius: 3px !important;
}

.epm-ribbon-count {
    font-family: var(--font-mono) !important;
    font-size: 9.5px !important;
    color: #64748b !important;
}

.epm-ribbon-controls {
    display: flex !important;
    align-items: center !important;
    gap: 4px !important;
    flex-wrap: nowrap !important;
}

.epm-density-group {
    display: inline-flex !important;
    align-items: center !important;
    gap: 2px !important;
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 3px !important;
    padding: 1px 3px !important;
    height: 22px !important;
}

.epm-control-label {
    font-family: var(--font-sans) !important;
    font-size: 9px !important;
    font-weight: 700 !important;
    color: #64748b !important;
    text-transform: uppercase !important;
    margin-right: 2px !important;
}

.epm-density-btn {
    border: none !important;
    background: transparent !important;
    font-family: var(--font-sans) !important;
    font-size: 9.5px !important;
    font-weight: 600 !important;
    color: #475569 !important;
    padding: 1px 4px !important;
    border-radius: 2px !important;
    cursor: pointer !important;
    transition: all 0.12s ease !important;
}

.epm-density-btn:hover {
    color: #0f172a !important;
    background: #f1f5f9 !important;
}

.epm-density-btn.active {
    background: #0f172a !important;
    color: #ffffff !important;
}

.epm-ribbon-btn {
    display: inline-flex !important;
    align-items: center !important;
    gap: 3px !important;
    height: 22px !important;
    padding: 0 6px !important;
    font-family: var(--font-sans) !important;
    font-size: 10px !important;
    font-weight: 600 !important;
    color: #334155 !important;
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 3px !important;
    cursor: pointer !important;
    transition: all 0.12s ease !important;
}

.epm-ribbon-btn:hover {
    background: #f1f5f9 !important;
    color: #0f172a !important;
    border-color: #94a3b8 !important;
}

.epm-collapse-btn {
    width: 22px !important;
    padding: 0 !important;
    justify-content: center !important;
    font-size: 12px !important;
    font-weight: 700 !important;
}

/* Tab 1 Header Strip */
#tab1_header_strip {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 8px !important;
    margin-top: 4px !important;
    margin-bottom: 0 !important;
}

#tab1_header_strip .epm-table-ribbon {
    flex: 1 1 auto !important;
    margin-top: 0 !important;
}

#tab1_refresh_btn {
    height: 28px !important;
    min-height: 28px !important;
    font-size: 11px !important;
    padding: 0 10px !important;
    margin: 0 !important;
    border-radius: 4px !important;
    font-weight: 600 !important;
    white-space: nowrap !important;
}

/* Tab 2 & Tab 3 Ultra-Compact Filter Rows */
#cal_filters_row, #circ_filters_row {
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
    margin: 3px 0 !important;
    padding: 0 !important;
    flex-wrap: nowrap !important;
    overflow-x: auto !important;
    min-height: 28px !important;
}

#cal_filters_row .gradio-radio, #circ_filters_row .gradio-radio {
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

#cal_filters_row .gradio-radio > label, #circ_filters_row .gradio-radio > label,
#cal_filters_row .gradio-radio > .block-title, #circ_filters_row .gradio-radio > .block-title {
    display: none !important;
}

#cal_filters_row .wrap, #circ_filters_row .wrap {
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    gap: 3px !important;
    margin: 0 !important;
    padding: 0 !important;
    flex-wrap: nowrap !important;
}

#cal_filters_row .wrap label, #circ_filters_row .wrap label {
    display: inline-flex !important;
    align-items: center !important;
    height: 24px !important;
    padding: 0 7px !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 12px !important;
    background: #ffffff !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    color: #475569 !important;
    cursor: pointer !important;
    margin: 0 !important;
    transition: all 0.12s ease !important;
    white-space: nowrap !important;
}

#cal_filters_row .wrap label:hover, #circ_filters_row .wrap label:hover {
    background: #f1f5f9 !important;
    color: #0f172a !important;
    border-color: #94a3b8 !important;
}

#cal_filters_row .wrap label:has(input:checked), #circ_filters_row .wrap label:has(input:checked) {
    background: #ffffff !important;
    color: #1d4ed8 !important;
    border: 1.5px solid #2563eb !important;
    box-shadow: 0 1px 2px rgba(37, 99, 235, 0.12) !important;
    font-weight: 700 !important;
}

#cal_filters_row .wrap input[type="radio"], #circ_filters_row .wrap input[type="radio"] {
    display: none !important;
}

#circ_filters_row .gradio-textbox {
    margin: 0 !important;
    padding: 0 !important;
    min-height: 24px !important;
    flex: 1 1 auto !important;
}

#circ_filters_row .gradio-textbox label,
#circ_filters_row .gradio-textbox .block-title {
    display: none !important;
}

#circ_filters_row .gradio-textbox input {
    height: 24px !important;
    padding: 1px 8px !important;
    font-size: 11px !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 4px !important;
}

/* Table container styling directly under ribbon */
.epm-table-ribbon + div[id*="_table"] .table-wrap,
.epm-table-ribbon + div[id*="_table"] .gradio-dataframe,
.epm-table-ribbon + div[id*="_table"] div[data-testid="dataframe"],
.epm-table-ribbon + div[id*="_table"] .table-container {
    border-top-left-radius: 0 !important;
    border-top-right-radius: 0 !important;
    border-top: none !important;
}

/* Multi-Density Rules */
/* Density Compact (2-line clamp) */
div[id*="_table"].density-compact tbody td,
.density-compact tbody td {
    padding: 4px 6px !important;
    font-size: 11.5px !important;
    line-height: 1.3 !important;
}

div[id*="_table"].density-compact tbody td:nth-child(4) > *,
div[id*="_table"].density-compact tbody td:nth-child(4) a,
div[id*="_table"].density-compact tbody td:nth-child(5) > *,
div[id*="_table"].density-compact tbody td:nth-child(6) > *,
div[id*="_table"].density-compact tbody td:nth-child(7) > *,
div[id*="_table"].density-compact tbody td:nth-child(13) > * {
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    max-height: 2.7em !important;
}

/* Density Standard (4-line clamp) */
div[id*="_table"].density-standard tbody td,
.density-standard tbody td {
    padding: 7px 9px !important;
    font-size: 12px !important;
    line-height: 1.35 !important;
}

div[id*="_table"].density-standard tbody td:nth-child(4) > *,
div[id*="_table"].density-standard tbody td:nth-child(4) a,
div[id*="_table"].density-standard tbody td:nth-child(5) > *,
div[id*="_table"].density-standard tbody td:nth-child(6) > *,
div[id*="_table"].density-standard tbody td:nth-child(7) > *,
div[id*="_table"].density-standard tbody td:nth-child(13) > * {
    display: -webkit-box !important;
    -webkit-line-clamp: 4 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    max-height: 5.5em !important;
}

/* Density Expanded (Full Unconstrained Text) */
div[id*="_table"].density-expanded tbody td,
.density-expanded tbody td {
    padding: 9px 12px !important;
    font-size: 12.5px !important;
    line-height: 1.45 !important;
}

div[id*="_table"].density-expanded tbody td:nth-child(4) > *,
div[id*="_table"].density-expanded tbody td:nth-child(4) a,
div[id*="_table"].density-expanded tbody td:nth-child(5) > *,
div[id*="_table"].density-expanded tbody td:nth-child(6) > *,
div[id*="_table"].density-expanded tbody td:nth-child(7) > *,
div[id*="_table"].density-expanded tbody td:nth-child(13) > * {
    display: block !important;
    -webkit-line-clamp: unset !important;
    max-height: none !important;
    overflow: visible !important;
    text-overflow: clip !important;
}

/* Collapsed Table State */
div[id*="_table"].epm-table-collapsed .table-wrap,
div[id*="_table"].epm-table-collapsed table,
div[id*="_table"].epm-table-collapsed div[data-testid="dataframe"],
div[id*="_table"].epm-table-collapsed .table-container {
    max-height: 0 !important;
    min-height: 0 !important;
    height: 0 !important;
    overflow: hidden !important;
    opacity: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

/* 17. Full-Screen Focus Mode & Floating Banner */
.epm-fullscreen-active {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    background: #ffffff !important;
    z-index: 99990 !important;
    padding: 60px 24px 24px 24px !important;
    overflow-y: auto !important;
    box-sizing: border-box !important;
}

.epm-fullscreen-active .table-wrap,
.epm-fullscreen-active table,
.epm-fullscreen-active .gradio-dataframe {
    width: 100% !important;
    max-height: none !important;
    height: auto !important;
}

.epm-focus-banner {
    position: fixed !important;
    top: 12px !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    z-index: 99999 !important;
    background: #0f172a !important;
    color: #ffffff !important;
    padding: 8px 18px !important;
    border-radius: 30px !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25) !important;
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    font-size: 12px !important;
    font-family: var(--font-sans) !important;
}

.epm-focus-banner-content {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
}

.epm-focus-exit-btn {
    background: #ef4444 !important;
    color: #ffffff !important;
    border: none !important;
    padding: 3px 10px !important;
    border-radius: 15px !important;
    font-weight: 700 !important;
    font-size: 11px !important;
    cursor: pointer !important;
    transition: background 0.15s ease !important;
}

.epm-focus-exit-btn:hover {
    background: #dc2626 !important;
}

.epm-focus-body-lock {
    overflow: hidden !important;
}

/* 18. Watchlist Highlighter & Glow */
tbody tr.epm-highlight-row td {
    background-color: #f0f7ff !important;
    border-top: 1px solid #bfdbfe !important;
    border-bottom: 1px solid #bfdbfe !important;
    font-weight: 600 !important;
}

tbody tr.epm-highlight-row td:first-child {
    border-left: 3px solid #2563eb !important;
}

"""


TOP_NAVBAR_HTML = """
<div id="epm-top-navbar" class="epm-top-navbar">
    <!-- Row 1: Brand Identity, Live Telemetry & Macro Ticker Strip -->
    <div class="epm-nav-row-1">
        <!-- Brand Cluster & Compact System Telemetry -->
        <div class="epm-nav-brand-cluster">
            <span class="epm-nav-logo">📰</span>
            <span class="epm-nav-title">EPM PRO</span>
            <span class="epm-nav-version">v3.0</span>
            <div class="epm-nav-status-badge">
                <span class="epm-live-dot"></span>
                <span>LIVE</span>
            </div>
            <!-- High-Density Inline System Telemetry -->
            <div class="epm-nav-telemetry">
                <span class="epm-telem-pill epm-telem-online" title="System Engine Online">🟢 ONLINE</span>
                <span class="epm-telem-pill" title="Cached Live News Catalysts">📰 <b id="epm-hdr-news">88</b></span>
                <span class="epm-telem-pill" title="5-Market Scheduled Events">📅 <b id="epm-hdr-cal">872</b></span>
                <span class="epm-telem-pill" title="Official Regulatory Circulars">📜 <b id="epm-hdr-circ">23</b></span>
                <span class="epm-telem-pill" title="Telegram Forwarder Status">📡 <b id="epm-hdr-tg">TG OK</b></span>
                <span class="epm-telem-pill" title="Current Time (IST)">⏱️ <b id="epm-hdr-ist">12:50 IST</b></span>
            </div>
        </div>

        <!-- Live Macro Ticker Ribbon -->
        <div class="epm-telemetry-strip" id="epm-telemetry-ticker">
            <div class="epm-ticker-item" title="Nifty 50 Index (NSE)">
                <span class="epm-ticker-sym">NIFTY 50</span>
                <span class="epm-ticker-val">24,850.35</span>
                <span class="epm-ticker-chg up">▲ +0.42%</span>
            </div>
            <div class="epm-ticker-divider"></div>
            <div class="epm-ticker-item" title="BSE Sensex">
                <span class="epm-ticker-sym">SENSEX</span>
                <span class="epm-ticker-val">81,420.10</span>
                <span class="epm-ticker-chg up">▲ +0.38%</span>
            </div>
            <div class="epm-ticker-divider"></div>
            <div class="epm-ticker-item" title="India Volatility Index">
                <span class="epm-ticker-sym">INDIA VIX</span>
                <span class="epm-ticker-val">13.15</span>
                <span class="epm-ticker-chg down">▼ -2.10%</span>
            </div>
            <div class="epm-ticker-divider"></div>
            <div class="epm-ticker-item" title="Brent Crude Oil Spot ($/bbl)">
                <span class="epm-ticker-sym">BRENT</span>
                <span class="epm-ticker-val">$74.20</span>
                <span class="epm-ticker-chg up">▲ +0.54%</span>
            </div>
            <div class="epm-ticker-divider"></div>
            <div class="epm-ticker-item" title="Spot Gold ($/oz)">
                <span class="epm-ticker-sym">GOLD</span>
                <span class="epm-ticker-val">$2,654.80</span>
                <span class="epm-ticker-chg up">▲ +0.15%</span>
            </div>
            <div class="epm-ticker-divider"></div>
            <div class="epm-ticker-item" title="US Dollar vs Indian Rupee">
                <span class="epm-ticker-sym">USD/INR</span>
                <span class="epm-ticker-val">₹84.05</span>
                <span class="epm-ticker-chg down">▼ -0.02%</span>
            </div>
            <div class="epm-ticker-divider"></div>
            <div class="epm-ticker-item" title="US Dollar Index">
                <span class="epm-ticker-sym">DXY</span>
                <span class="epm-ticker-val">103.85</span>
                <span class="epm-ticker-chg up">▲ +0.12%</span>
            </div>
        </div>
    </div>

    <!-- Row 2: Unified Navigation Tabs (Left) + Quick Utilities (Right) on ONE line -->
    <div class="epm-nav-row-2">
        <!-- 5 Page Navigation Tabs -->
        <div class="epm-quick-tabs-container">
            <button type="button" class="epm-tab-pill active" onclick="window.epmSwitchTab(0, this)">
                <span class="epm-tab-pill-icon">📰</span>
                <span>Live Wire</span>
            </button>
            <button type="button" class="epm-tab-pill" onclick="window.epmSwitchTab(1, this)">
                <span class="epm-tab-pill-icon">📅</span>
                <span>Market Calendar</span>
            </button>
            <button type="button" class="epm-tab-pill" onclick="window.epmSwitchTab(2, this)">
                <span class="epm-tab-pill-icon">📜</span>
                <span>Regulatory Circulars</span>
            </button>
            <button type="button" class="epm-tab-pill" onclick="window.epmSwitchTab(3, this)">
                <span class="epm-tab-pill-icon">⚙️</span>
                <span>Settings Hub</span>
            </button>
            <button type="button" class="epm-tab-pill" onclick="window.epmSwitchTab(4, this)">
                <span class="epm-tab-pill-icon">❓</span>
                <span>User Guide</span>
            </button>
        </div>

        <!-- Quick Utilities & Actions -->
        <div class="epm-nav-controls">
            <!-- Watchlist Highlighter Input -->
            <div class="epm-nav-search-wrap" title="Highlight table rows matching keywords/tickers">
                <span class="epm-nav-search-icon">🔍</span>
                <input id="epm-watchlist-input" type="text" placeholder="Highlight Ticker..." oninput="window.epmApplyWatchlist(this.value)">
                <span id="epm-watchlist-count" class="epm-watchlist-badge" style="display:none;">0</span>
                <button type="button" class="epm-watchlist-clear-btn" onclick="window.epmClearWatchlist()" title="Clear highlighter">✕</button>
            </div>

            <!-- Global Density Toggle -->
            <button type="button" id="epm-global-density-btn" class="epm-top-btn" onclick="window.epmCycleGlobalDensity()" title="Cycle all tables density (Compact / Standard / Expanded)">
                <span class="epm-btn-icon">≡</span>
                <span id="epm-global-density-lbl">Compact</span>
            </button>

            <!-- Audio Alert Toggle -->
            <button type="button" id="epm-audio-toggle-btn" class="epm-top-btn epm-btn-active" onclick="window.epmToggleAudio()" title="Toggle Web Audio Flash Chime (880Hz -> 1320Hz)">
                <span class="epm-btn-icon">🔔</span>
                <span id="epm-audio-status-lbl">Audio ON</span>
            </button>

            <!-- Quick Resource Links -->
            <a href="/api/calendar/ics" target="_blank" class="epm-nav-link" title="RFC-5545 iCalendar Subscription Feed">📅 iCal</a>
            <a href="/docs" target="_blank" class="epm-nav-link" title="OpenAPI / Swagger REST API Docs">⚡ API</a>
        </div>
    </div>
</div>
"""



TERMINAL_CLIENT_JS = r"""
// EPM PRO INSTITUTIONAL CLIENT ENGINE 3.0
(function() {
    // 1. Audio Engine (Dual-tone Harmonic 880Hz -> 1320Hz Sine Wave)
    let audioCtx = null;
    let audioMuted = localStorage.getItem("epm_audio_muted") === "true";

    function getAudioCtx() {
        if (!audioCtx) {
            const AC = window.AudioContext || window.webkitAudioContext;
            if (AC) audioCtx = new AC();
        }
        if (audioCtx && audioCtx.state === 'suspended') {
            audioCtx.resume();
        }
        return audioCtx;
    }

    window.epmPlayChime = function(force = false) {
        if (audioMuted && !force) return;
        try {
            const ctx = getAudioCtx();
            if (!ctx) return;
            const now = ctx.currentTime;
            
            // Oscillator 1 (880Hz -> 1320Hz)
            const osc1 = ctx.createOscillator();
            const gain1 = ctx.createGain();
            osc1.type = 'sine';
            osc1.frequency.setValueAtTime(880, now);
            osc1.frequency.exponentialRampToValueAtTime(1320, now + 0.12);
            
            gain1.gain.setValueAtTime(0.001, now);
            gain1.gain.linearRampToValueAtTime(0.15, now + 0.02);
            gain1.gain.exponentialRampToValueAtTime(0.0001, now + 0.32);
            
            osc1.connect(gain1);
            gain1.connect(ctx.destination);
            
            // Oscillator 2 (1320Hz -> 1760Hz)
            const osc2 = ctx.createOscillator();
            const gain2 = ctx.createGain();
            osc2.type = 'sine';
            osc2.frequency.setValueAtTime(1320, now + 0.04);
            osc2.frequency.exponentialRampToValueAtTime(1760, now + 0.16);
            
            gain2.gain.setValueAtTime(0.001, now + 0.04);
            gain2.gain.linearRampToValueAtTime(0.12, now + 0.06);
            gain2.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);
            
            osc2.connect(gain2);
            gain2.connect(ctx.destination);
            
            osc1.start(now);
            osc1.stop(now + 0.33);
            osc2.start(now + 0.04);
            osc2.stop(now + 0.36);
        } catch(e) {
            console.warn("[EPM Audio] Chime error:", e);
        }
    };

    window.epmToggleAudio = function() {
        audioMuted = !audioMuted;
        localStorage.setItem("epm_audio_muted", audioMuted);
        epmUpdateAudioUI();
        if (!audioMuted) {
            window.epmPlayChime(true);
        }
    };

    function epmUpdateAudioUI() {
        const lbl = document.getElementById("epm-audio-status-lbl");
        const btn = document.getElementById("epm-audio-toggle-btn");
        if (lbl) lbl.textContent = audioMuted ? "Audio OFF" : "Audio ON";
        if (btn) {
            if (audioMuted) {
                btn.classList.add("epm-btn-muted");
                btn.classList.remove("epm-btn-active");
            } else {
                btn.classList.remove("epm-btn-muted");
                btn.classList.add("epm-btn-active");
            }
        }
    }

    // 2. Tab Navigation Sync & Active Tab Indicator
    const TAB_NAMES = [
        "📰 LIVE FINANCIAL WIRE",
        "📅 MARKET CALENDAR & OUTCOMES",
        "📜 REGULATORY CIRCULARS & PDFS",
        "⚙️ PORTAL SETTINGS & INTEGRATIONS",
        "❓ USER GUIDE & MANUAL"
    ];

    window.epmSwitchTab = function(tabIdx, pillEl) {
        const tabBtns = document.querySelectorAll('button[role="tab"]');
        if (tabBtns && tabBtns[tabIdx]) {
            tabBtns[tabIdx].click();
            epmSyncActiveTab(tabIdx);
        }
    };

    function epmSyncActiveTab(tabIdx) {
        const pills = document.querySelectorAll('.epm-tab-pill');
        pills.forEach((p, idx) => {
            if (idx === tabIdx) p.classList.add('active');
            else p.classList.remove('active');
        });
        const badge = document.getElementById("epm-active-tab-indicator");
        if (badge && TAB_NAMES[tabIdx]) {
            badge.textContent = TAB_NAMES[tabIdx];
        }
    }

    // 3. Density Controller (Compact / Standard / Expanded)
    const DENSITIES = ['compact', 'standard', 'expanded'];
    let currentGlobalDensity = localStorage.getItem("epm_global_density") || "compact";

    window.epmSetDensity = function(tableId, density, btn) {
        const target = document.getElementById(tableId);
        if (!target) return;
        
        target.classList.remove("density-compact", "density-standard", "density-expanded");
        target.classList.add("density-" + density);
        
        const ribbon = document.querySelector(`.epm-table-ribbon[data-target="${tableId}"]`);
        if (ribbon) {
            ribbon.querySelectorAll(".epm-density-btn").forEach(b => {
                if (b.dataset.density === density) b.classList.add("active");
                else b.classList.remove("active");
            });
        }
        localStorage.setItem("epm_density_" + tableId, density);
    };

    window.epmCycleGlobalDensity = function() {
        let idx = DENSITIES.indexOf(currentGlobalDensity);
        idx = (idx + 1) % DENSITIES.length;
        const nextDensity = DENSITIES[idx];
        window.epmSetGlobalDensity(nextDensity);
    };

    window.epmSetGlobalDensity = function(density) {
        currentGlobalDensity = density;
        localStorage.setItem("epm_global_density", density);
        const lbl = document.getElementById("epm-global-density-lbl");
        if (lbl) lbl.textContent = density.charAt(0).toUpperCase() + density.slice(1);
        
        const tables = ['top_news_table', 'bottom_news_table', 'calendar_table', 'holidays_table', 'circ_table'];
        tables.forEach(tid => {
            window.epmSetDensity(tid, density);
        });
    };

    // 4. Table Collapse / Expand Controller
    window.epmToggleCollapse = function(tableId, btn) {
        const target = document.getElementById(tableId);
        if (!target) return;
        const isCollapsed = target.classList.toggle("epm-table-collapsed");
        if (btn) {
            const sp = btn.querySelector("span") || btn;
            sp.textContent = isCollapsed ? "+" : "−";
            btn.title = isCollapsed ? "Expand table" : "Collapse table";
        }
        localStorage.setItem("epm_collapsed_" + tableId, isCollapsed ? "true" : "false");
    };

    // 5. Table CSV Exporter (RFC-4180 with UTF-8 BOM)
    window.epmExportCSV = function(tableId) {
        const tableWrap = document.getElementById(tableId);
        if (!tableWrap) {
            alert("Table container not found: " + tableId);
            return;
        }
        const table = tableWrap.querySelector("table");
        if (!table) {
            alert("Table data is still loading...");
            return;
        }
        
        const lines = [];
        const ths = table.querySelectorAll("thead th");
        const headers = [];
        ths.forEach(th => {
            let t = th.innerText.trim().replace(/\r?\n|\r/g, " ");
            headers.push('"' + t.replace(/"/g, '""') + '"');
        });
        if (headers.length > 0) lines.push(headers.join(","));
        
        const trs = table.querySelectorAll("tbody tr");
        trs.forEach(tr => {
            const tds = tr.querySelectorAll("td");
            const row = [];
            tds.forEach(td => {
                let t = td.innerText.trim().replace(/\r?\n|\r/g, " ");
                row.push('"' + t.replace(/"/g, '""') + '"');
            });
            if (row.length > 0) lines.push(row.join(","));
        });
        
        if (lines.length <= 1) {
            alert("No records found in " + tableId);
            return;
        }
        
        const csvContent = "\uFEFF" + lines.join("\r\n");
        const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        const dateStr = new Date().toISOString().slice(0, 10);
        a.href = url;
        a.download = `epm_${tableId}_${dateStr}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    // 6. Full-Screen Focus Mode
    let currentFocusedTable = null;

    window.epmToggleFocus = function(tableId) {
        const tableWrap = document.getElementById(tableId);
        if (!tableWrap) return;
        
        if (currentFocusedTable === tableId) {
            window.epmExitFocus();
            return;
        }
        
        window.epmExitFocus();
        
        currentFocusedTable = tableId;
        tableWrap.classList.add("epm-fullscreen-active");
        document.body.classList.add("epm-focus-body-lock");
        
        let banner = document.getElementById("epm-focus-banner");
        if (!banner) {
            banner = document.createElement("div");
            banner.id = "epm-focus-banner";
            banner.className = "epm-focus-banner";
            document.body.appendChild(banner);
        }
        banner.innerHTML = `
            <div class="epm-focus-banner-content">
                <span>⛶ <b>INSTITUTIONAL FULL-SCREEN FOCUS:</b> <code>${tableId.toUpperCase()}</code> · Press <kbd style="background:#334155;color:#fff;padding:1px 5px;border-radius:3px;">ESC</kbd> to return</span>
                <button onclick="window.epmExitFocus()" class="epm-focus-exit-btn">✕ Exit Focus</button>
            </div>
        `;
        banner.style.display = "flex";
    };

    window.epmExitFocus = function() {
        if (!currentFocusedTable) return;
        const target = document.getElementById(currentFocusedTable);
        if (target) target.classList.remove("epm-fullscreen-active");
        currentFocusedTable = null;
        document.body.classList.remove("epm-focus-body-lock");
        const banner = document.getElementById("epm-focus-banner");
        if (banner) banner.style.display = "none";
    };

    // 7. Watchlist / Ticker Highlighter
    window.epmApplyWatchlist = function(val) {
        let query = (typeof val === 'string') ? val : (localStorage.getItem("epm_watchlist") || "");
        localStorage.setItem("epm_watchlist", query);
        
        const input = document.getElementById("epm-watchlist-input");
        if (input && input.value !== query) input.value = query;
        
        const tokens = query.toLowerCase().split(/[,\s]+/).map(s => s.trim()).filter(s => s.length >= 2);
        const tables = ['top_news_table', 'bottom_news_table', 'calendar_table', 'holidays_table', 'circ_table'];
        let totalMatches = 0;
        
        tables.forEach(tid => {
            const wrap = document.getElementById(tid);
            if (!wrap) return;
            const rows = wrap.querySelectorAll("tbody tr");
            rows.forEach(tr => {
                if (tokens.length === 0) {
                    tr.classList.remove("epm-highlight-row");
                    return;
                }
                const text = tr.innerText.toLowerCase();
                const matched = tokens.some(tok => text.includes(tok));
                if (matched) {
                    tr.classList.add("epm-highlight-row");
                    totalMatches++;
                } else {
                    tr.classList.remove("epm-highlight-row");
                }
            });
        });
        
        const badge = document.getElementById("epm-watchlist-count");
        if (badge) {
            if (tokens.length > 0) {
                badge.textContent = `${totalMatches} match${totalMatches === 1 ? '' : 'es'}`;
                badge.style.display = "inline-flex";
            } else {
                badge.style.display = "none";
            }
        }
    };

    window.epmClearWatchlist = function() {
        const input = document.getElementById("epm-watchlist-input");
        if (input) input.value = "";
        window.epmApplyWatchlist("");
    };

    // 8. Action Drawers (Tab 2 Calendar Toolbar & Tab 3 Circulars Drawer)
    window.epmToggleCalDrawer = function() {
        const drawer = document.getElementById("cal_action_drawer");
        const btn = document.getElementById("cal_drawer_toggle");
        if (!drawer) return;
        const isCollapsed = drawer.classList.toggle("collapsed");
        if (btn) {
            const btnSpan = btn.querySelector("span") || btn;
            btnSpan.textContent = isCollapsed ? "🛠️ Tools (Expand)" : "✕ Hide Tools";
        }
        localStorage.setItem("epm_cal_drawer_collapsed", isCollapsed ? "true" : "false");
    };

    window.epmToggleCircDrawer = function() {
        const drawer = document.getElementById("circ_action_drawer");
        const btn = document.getElementById("circ_drawer_toggle");
        if (!drawer) return;
        const isCollapsed = drawer.classList.toggle("collapsed");
        if (btn) {
            const btnSpan = btn.querySelector("span") || btn;
            btnSpan.textContent = isCollapsed ? "🛠️ Tools (Expand)" : "✕ Hide Tools";
        }
        localStorage.setItem("epm_circ_drawer_collapsed", isCollapsed ? "true" : "false");
    };

    // 9. IST Clock & Status Telemetry Sync Engine
    function updateISTClock() {
        try {
            const now = new Date();
            const options = { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
            const istStr = new Intl.DateTimeFormat([], options).format(now);
            const clockEl = document.getElementById("epm-hdr-ist");
            if (clockEl) clockEl.textContent = istStr + " IST";
        } catch(e) {}
    }
    setInterval(updateISTClock, 1000);

    function syncTelemetryFromStatusBox() {
        const box = document.getElementById("epm-status-box");
        if (!box) return;
        const txt = box.textContent || "";
        const mNews = txt.match(/Cached News:\s*(\d+)/i);
        if (mNews && document.getElementById("epm-hdr-news")) {
            document.getElementById("epm-hdr-news").textContent = mNews[1];
        }
        const mCal = txt.match(/Multi-Market Events:\s*(\d+)/i);
        if (mCal && document.getElementById("epm-hdr-cal")) {
            document.getElementById("epm-hdr-cal").textContent = mCal[1];
        }
        const mCirc = txt.match(/Regulatory Circulars:\s*(\d+)/i);
        if (mCirc && document.getElementById("epm-hdr-circ")) {
            document.getElementById("epm-hdr-circ").textContent = mCirc[1];
        }
    }
    setInterval(syncTelemetryFromStatusBox, 2000);

    window.addEventListener("keydown", function(e) {
        if (e.key === "Escape") {
            if (currentFocusedTable) {
                window.epmExitFocus();
                return;
            }
        }
    });

    // 10. Initialization & Observer
    function epmInitTerminal() {
        epmUpdateAudioUI();
        window.epmSetGlobalDensity(currentGlobalDensity);
        updateISTClock();
        syncTelemetryFromStatusBox();
        
        // Default action drawers to collapsed for ultra-compact vertical footprint
        const calCollapsed = localStorage.getItem("epm_cal_drawer_collapsed") !== "false";
        const cDrawer = document.getElementById("cal_action_drawer");
        const cBtn = document.getElementById("cal_drawer_toggle");
        if (cDrawer && calCollapsed) cDrawer.classList.add("collapsed");
        if (cBtn) {
            const s = cBtn.querySelector("span") || cBtn;
            s.textContent = calCollapsed ? "🛠️ Tools (Expand)" : "✕ Hide Tools";
        }
        
        const circCollapsed = localStorage.getItem("epm_circ_drawer_collapsed") !== "false";
        const crDrawer = document.getElementById("circ_action_drawer");
        const crBtn = document.getElementById("circ_drawer_toggle");
        if (crDrawer && circCollapsed) crDrawer.classList.add("collapsed");
        if (crBtn) {
            const s = crBtn.querySelector("span") || crBtn;
            s.textContent = circCollapsed ? "🛠️ Tools (Expand)" : "✕ Hide Tools";
        }
        
        const savedQuery = localStorage.getItem("epm_watchlist") || "";
        if (savedQuery) {
            window.epmApplyWatchlist(savedQuery);
        }
        
        function hideGradioTabs() {
            const defaultTabs = document.querySelectorAll('.tab-wrapper, div[role="tablist"], .tab-container:not(.visually-hidden), .tab-nav');
            defaultTabs.forEach(el => {
                el.style.setProperty('height', '0px', 'important');
                el.style.setProperty('max-height', '0px', 'important');
                el.style.setProperty('min-height', '0px', 'important');
                el.style.setProperty('padding', '0', 'important');
                el.style.setProperty('margin', '0', 'important');
                el.style.setProperty('opacity', '0', 'important');
                el.style.setProperty('pointer-events', 'none', 'important');
                el.style.setProperty('visibility', 'hidden', 'important');
                el.style.setProperty('overflow', 'hidden', 'important');
                el.style.setProperty('border', 'none', 'important');
            });
        }
        hideGradioTabs();

        const tabBtns = document.querySelectorAll('button[role="tab"]');
        tabBtns.forEach((btn, idx) => {
            btn.addEventListener("click", () => {
                epmSyncActiveTab(idx);
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", epmInitTerminal);
    } else {
        epmInitTerminal();
    }
    window.addEventListener("load", epmInitTerminal);
    
    setInterval(() => {
        const savedQuery = localStorage.getItem("epm_watchlist");
        if (savedQuery) window.epmApplyWatchlist(savedQuery);
        
        const defaultTabs = document.querySelectorAll('.tab-wrapper, div[role="tablist"], .tab-container:not(.visually-hidden)');
        defaultTabs.forEach(el => {
            if (el.offsetHeight > 0) {
                el.style.setProperty('height', '0px', 'important');
                el.style.setProperty('visibility', 'hidden', 'important');
                el.style.setProperty('overflow', 'hidden', 'important');
            }
        });
    }, 1500);
})();
"""



# ─── Build Gradio Blocks UI ──────────────────────────────────────────────────

# Pre-computed initial states for instantaneous zero-error load across all tabs
init_status_str, init_news_html, init_top_rows, init_bottom_rows = get_dashboard_tables()
init_cal_summary, init_cal_html, init_cal_rows, init_hol_rows = get_calendar_tables()
init_circ_summary, init_circ_html, init_circ_rows = get_circulars_view()

with gr.Blocks(title="EPM Pro Global Financial News & Multi-Market Intelligence Terminal", fill_width=True) as demo:
    gr.HTML("<style>" + CUSTOM_CSS + "</style>" + TOP_NAVBAR_HTML + "<script>" + TERMINAL_CLIENT_JS + "</script>")
    status_box = gr.Markdown(value=init_status_str, elem_id="epm-status-box")

    with gr.Tabs(overflow_behavior="wrap"):
        # ═══════════════════════════════════════════════════════════
        # TAB 1: Live Financial Wire & Breaking Catalysts
        # ═══════════════════════════════════════════════════════════
        with gr.TabItem("📰 Live Financial Wire & Breaking Catalysts"):
            with gr.Row(elem_id="tab1_header_strip"):
                gr.HTML(render_table_ribbon("top_news_table", "Institutional Breaking Wire", subtitle="AI Scored ≥ 7", count_badge="Primary Catalysts"))
                refresh_btn = gr.Button("🔄 Force Refresh Feeds", variant="primary", elem_id="tab1_refresh_btn", scale=0)

            top_table = gr.Dataframe(
                headers=["Score", "Sentiment", "Impact", "Headline", "Sectors/Tickers", "AI Reasoning", "Source", "Relevance", "Time"],
                datatype=["str", "str", "str", "markdown", "str", "str", "str", "str", "str"],
                value=init_top_rows,
                interactive=False,
                wrap=True,
                elem_id="top_news_table"
            )

            gr.HTML(render_table_ribbon("bottom_news_table", "Broad Market Secondary Stream", subtitle="All Feeds", count_badge="Raw Wire"))
            bottom_table = gr.Dataframe(
                headers=["Time", "Source", "Headline", "Relevance", "Sentiment", "URL"],
                datatype=["str", "str", "markdown", "str", "str", "markdown"],
                value=init_bottom_rows,
                interactive=False,
                wrap=True,
                elem_id="bottom_news_table"
            )

            with gr.Accordion("🎴 Visual News Cards Feed (Alternative Expanded View)", open=False):
                top_news_visual = gr.HTML(value=init_news_html, elem_id="news_visual_feed")

            with gr.Accordion("⚡ Live AI Impact & Sentiment Tester", open=False):
                with gr.Row():
                    test_title = gr.Textbox(label="Headline / Breaking News", placeholder="e.g. RBI unexpectedly cuts interest rates by 25 bps")
                    test_desc = gr.Textbox(label="Summary (Optional)", placeholder="Context details...")
                analyze_btn = gr.Button("Analyze Headline with Gemini 2.5", variant="primary")
                ai_output = gr.Markdown()
                analyze_btn.click(test_ai_rating, inputs=[test_title, test_desc], outputs=ai_output)

        # ═══════════════════════════════════════════════════════════
        # TAB 2: Multi-Market Calendar, Live Timers & Outcomes
        # ═══════════════════════════════════════════════════════════
        with gr.TabItem("📅 Market Calendar, Timers & Outcomes"):
            cal_info_bar = gr.Markdown(value=init_cal_summary, elem_id="cal_info_bar")

            with gr.Row(elem_id="cal_filters_row"):
                cal_market_filter = gr.Radio(
                    choices=[
                        ("🌐 ALL", "ALL"),
                        ("🇮🇳 NSE", "NSE"),
                        ("🇮🇳 BSE", "BSE"),
                        ("⛽ MCX", "MCX"),
                        ("₿ CRYPTO", "CRYPTO"),
                        ("🇺🇸 NYSE", "NYSE")
                    ],
                    value="ALL",
                    label="",
                    show_label=False,
                    scale=3
                )
                cal_filter = gr.Radio(
                    choices=[
                        ("All Scheduled", "all"),
                        ("Today (7 AM)", "today"),
                        ("Tomorrow (7 AM)", "tomorrow"),
                        ("7 Days", "week"),
                        ("Active Timers", "upcoming")
                    ],
                    value="all",
                    label="",
                    show_label=False,
                    scale=3
                )
                cal_drawer_toggle = gr.Button("🛠️ Tools (Expand)", elem_id="cal_drawer_toggle", variant="secondary", scale=0)

            with gr.Column(elem_id="cal_action_drawer", elem_classes=["epm-action-drawer", "collapsed"]):
                with gr.Row():
                    cal_sync_btn = gr.Button("🔄 Sync 5 Markets & Timers", variant="primary", scale=1)
                    btn_sync_gcal = gr.Button("📅 Sync Google Calendar", variant="secondary", scale=1)
                    btn_push_today_photo = gr.Button("📸 Send Today's Photo Cards", variant="secondary", scale=1)
                    btn_push_tomorrow_photo = gr.Button("📸 Send Tomorrow's Photo Cards", variant="secondary", scale=1)

                with gr.Row():
                    btn_push_holiday = gr.Button("🏖️ Send Next-Day Holiday Check", variant="secondary", scale=1)
                    btn_push_weekly = gr.Button("📲 Resend Weekly Sync Links", variant="secondary", scale=1)
                    btn_push_today = gr.Button("💬 Send Today's Text Snapshot", variant="secondary", scale=1)
                    btn_push_tomorrow = gr.Button("💬 Send Tomorrow's Text Snapshot", variant="secondary", scale=1)

            cal_action_msg = gr.Markdown(elem_id="cal_action_msg")

            gr.HTML(render_table_ribbon("calendar_table", "Multi-Market Catalyst Schedule & Historical Outcomes", subtitle="5 Bourses", count_badge="Live Timers"))
            calendar_table = gr.Dataframe(
                headers=[
                    "Event ID",
                    "Market",
                    "Date",
                    "Time (IST)",
                    "⏱ Live Timer",
                    "Asset / Symbol",
                    "Market Event / Corporate Release",
                    "Impact",
                    "Previous",
                    "Forecast",
                    "🏁 Actual / Outcome",
                    "📊 Verdict",
                    "🔗 Linked News / GCal"
                ],
                datatype=["str", "str", "str", "str", "str", "str", "str", "str", "str", "str", "str", "str", "markdown"],
                value=init_cal_rows,
                interactive=False,
                wrap=True,
                elem_id="calendar_table"
            )

            with gr.Accordion("🎴 Visual Catalyst Countdown Feed (Cards View)", open=False):
                calendar_visual_feed = gr.HTML(value=init_cal_html, elem_id="calendar_visual_feed")

            gr.HTML(render_table_ribbon("holidays_table", "2026 Authoritative Trading Holidays", subtitle="NSE · BSE · MCX · NYSE · CRYPTO", count_badge="All Sessions"))
            holidays_table = gr.Dataframe(
                headers=[
                    "Date",
                    "Day",
                    "Holiday / Occasion",
                    "🇮🇳 NSE Status",
                    "🇮🇳 BSE Status",
                    "⛽ MCX Status (Morning / Evening)",
                    "🇺🇸 NYSE Status (EST / IST)",
                    "₿ Crypto Status"
                ],
                datatype=["str", "str", "str", "str", "str", "str", "str", "str"],
                value=init_hol_rows,
                interactive=False,
                wrap=True,
                elem_id="holidays_table"
            )

            with gr.Accordion("✏️ Record Event Outcome Manually or Add Custom Event", open=False):
                gr.Markdown("Enter an existing **Event ID** to update its outcome (e.g. `nse_reliance_res`), or leave blank to log a new scheduled release:")
                with gr.Row():
                    in_ev_id = gr.Textbox(label="Event ID (Optional for new)", placeholder="e.g. nse_reliance_res_2026-10-09")
                    in_ev_mkt = gr.Dropdown(choices=["NSE", "BSE", "MCX", "CRYPTO", "NYSE"], value="NSE", label="Market")
                    in_ev_date = gr.Textbox(label="Date (YYYY-MM-DD)", value=now_ist().strftime("%Y-%m-%d"))
                    in_ev_time = gr.Textbox(label="Time IST (HH:MM)", value="14:30")
                    in_ev_sym = gr.Textbox(label="Symbol / Ticker", value="🇮🇳 NSE:RELIANCE")
                    in_ev_imp = gr.Dropdown(choices=["HIGH", "MEDIUM", "LOW"], value="HIGH", label="Impact")
                with gr.Row():
                    in_ev_name = gr.Textbox(label="Event Title", placeholder="e.g. Reliance Q2 Results / US CPI / EIA Crude Inventory", scale=2)
                    in_ev_prev = gr.Textbox(label="Previous", placeholder="e.g. ₹41,100 Cr", scale=1)
                    in_ev_fore = gr.Textbox(label="Forecast", placeholder="e.g. ₹43,250 Cr", scale=1)
                    in_ev_act = gr.Textbox(label="Actual Outcome", value="⏳ Pending", placeholder="e.g. ₹44,180 Cr (Beats)", scale=1)
                    in_ev_sent = gr.Dropdown(
                        choices=["⏳ PENDING", "🟢 BULLISH", "🔴 BEARISH", "⚪ NEUTRAL"],
                        value="🟢 BULLISH",
                        label="Market Verdict",
                        scale=1
                    )
                with gr.Row():
                    in_ev_push = gr.Checkbox(value=True, label="Immediately forward this Individual Event & Outcome to the Calendar Telegram Channel")
                    save_ev_btn = gr.Button("💾 Save Event / Outcome & Dispatch Market Update", variant="primary")

            cal_filter.change(get_calendar_tables, inputs=[cal_filter, cal_market_filter], outputs=[cal_info_bar, calendar_visual_feed, calendar_table, holidays_table])
            cal_market_filter.change(get_calendar_tables, inputs=[cal_filter, cal_market_filter], outputs=[cal_info_bar, calendar_visual_feed, calendar_table, holidays_table])
            cal_sync_btn.click(sync_and_refresh_calendar, inputs=[cal_filter, cal_market_filter], outputs=[cal_info_bar, calendar_visual_feed, calendar_table, holidays_table])
            btn_sync_gcal.click(trigger_sync_google_cal, outputs=[cal_action_msg])
            btn_push_weekly.click(push_weekly_calendar_dispatch, outputs=[cal_action_msg])
            btn_push_today_photo.click(push_today_photo_snapshot_all_markets, outputs=[cal_action_msg])
            btn_push_tomorrow_photo.click(push_tomorrow_photo_snapshot_all_markets, outputs=[cal_action_msg])
            btn_push_today.click(push_today_snapshot_all_markets, outputs=[cal_action_msg])
            btn_push_tomorrow.click(push_tomorrow_snapshot_all_markets, outputs=[cal_action_msg])
            btn_push_holiday.click(push_holiday_check_alert, outputs=[cal_action_msg])
            save_ev_btn.click(
                handle_manual_event_save,
                inputs=[in_ev_id, in_ev_mkt, in_ev_date, in_ev_time, in_ev_sym, in_ev_name, in_ev_imp, in_ev_prev, in_ev_fore, in_ev_act, in_ev_sent, in_ev_push, cal_filter, cal_market_filter],
                outputs=[cal_action_msg, cal_info_bar, calendar_visual_feed, calendar_table]
            )
            cal_drawer_toggle.click(None, js="() => window.epmToggleCalDrawer()")

        # ═══════════════════════════════════════════════════════════
        # TAB 3: Official Regulatory Circulars & Notifications Repository
        # ═══════════════════════════════════════════════════════════
        with gr.TabItem("📜 Regulatory Circulars & Official PDFs"):
            circ_info_bar = gr.Markdown(value=init_circ_summary, elem_id="circ_info_bar")

            with gr.Row(elem_id="circ_filters_row"):
                circ_reg_filter = gr.Radio(
                    choices=[
                        ("🌐 ALL", "ALL"),
                        ("🇮🇳 NSE", "NSE"),
                        ("🇮🇳 BSE", "BSE"),
                        ("⛽ MCX", "MCX"),
                        ("🏛️ RBI", "RBI"),
                        ("🇮🇳 FINMIN", "FINMIN"),
                        ("🇺🇸 FOMC", "FOMC"),
                        ("🇺🇸 NYSE", "NYSE")
                    ],
                    value="ALL",
                    label="",
                    show_label=False,
                    scale=4
                )
                circ_imp_filter = gr.Radio(
                    choices=[
                        ("All", "ALL"),
                        ("🚨 High Impact", "HIGH")
                    ],
                    value="ALL",
                    label="",
                    show_label=False,
                    scale=1
                )
                circ_search = gr.Textbox(
                    placeholder="Search circulars / keywords...",
                    label="",
                    show_label=False,
                    scale=2
                )
                circ_drawer_toggle = gr.Button("🛠️ Tools (Expand)", elem_id="circ_drawer_toggle", variant="secondary", scale=0)

            with gr.Row(elem_id="circ_action_drawer", elem_classes=["epm-action-drawer", "collapsed"]):
                circ_refresh_btn = gr.Button("🔄 Check & Poll Latest Circulars", variant="primary", scale=1)
                circ_dispatch_btn = gr.Button("📲 Forward Latest Circular to Telegram", variant="secondary", scale=1)

            circ_action_msg = gr.Markdown(elem_id="circ_action_msg")

            gr.HTML(render_table_ribbon("circ_table", "Official Regulatory Documents Directory", subtitle="Verified PDFs", count_badge="Directives"))
            circ_table = gr.Dataframe(
                headers=[
                    "Regulator",
                    "Circular Ref No.",
                    "Date",
                    "Impact",
                    "Subject / Directive",
                    "Category",
                    "AI Executive Summary",
                    "Official PDF Document"
                ],
                datatype=["str", "str", "str", "str", "str", "str", "str", "markdown"],
                value=init_circ_rows,
                interactive=False,
                wrap=True,
                elem_id="circ_table"
            )

            with gr.Accordion("🎴 Visual Regulatory Stream & AI Breakdown Cards", open=False):
                circ_visual_feed = gr.HTML(value=init_circ_html, elem_id="circ_visual_feed")

            circ_reg_filter.change(
                get_circulars_view,
                inputs=[circ_reg_filter, circ_imp_filter, circ_search],
                outputs=[circ_info_bar, circ_visual_feed, circ_table]
            )
            circ_imp_filter.change(
                get_circulars_view,
                inputs=[circ_reg_filter, circ_imp_filter, circ_search],
                outputs=[circ_info_bar, circ_visual_feed, circ_table]
            )
            circ_search.submit(
                get_circulars_view,
                inputs=[circ_reg_filter, circ_imp_filter, circ_search],
                outputs=[circ_info_bar, circ_visual_feed, circ_table]
            )
            circ_refresh_btn.click(
                refresh_circulars_data,
                inputs=[circ_reg_filter, circ_imp_filter, circ_search],
                outputs=[circ_info_bar, circ_visual_feed, circ_table]
            )
            circ_dispatch_btn.click(
                dispatch_circular_to_telegram,
                inputs=[circ_reg_filter],
                outputs=[circ_action_msg]
            )
            circ_drawer_toggle.click(None, js="() => window.epmToggleCircDrawer()")

        # ═══════════════════════════════════════════════════════════
        # TAB 4: Portal Settings Page (Alert Channels, Google Cal & Sources)
        # ═══════════════════════════════════════════════════════════
        with gr.TabItem("⚙️ Portal Settings & Integrations"):
            gr.Markdown("### ⚙️ System Settings & External Integrations Hub", elem_id="settings_hdr")

            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### 📰 Channel 1: Live Breaking News Telegram")
                    adm_news_token = gr.Textbox(
                        label="News Bot Token",
                        value=telegram_notifier.bot_token,
                        type="password",
                        placeholder="Paste BotFather token..."
                    )
                    adm_news_chat = gr.Textbox(
                        label="News Channel / Group Chat ID",
                        value=telegram_notifier.chat_id,
                        placeholder="e.g. @my_news_channel or -1001234567890"
                    )
                    adm_news_enabled = gr.Checkbox(
                        label="Enable Live News Telegram Forwarding",
                        value=telegram_notifier.enabled
                    )
                    test_news_tg_btn = gr.Button("🔔 Send Test Message to News Channel")

                with gr.Column():
                    gr.Markdown("#### 📅 Channel 2: Market Calendar & Outcomes Telegram (Separate Group/Channel)")
                    adm_cal_token = gr.Textbox(
                        label="Calendar Bot Token (Leave blank to reuse News Bot Token)",
                        value=telegram_notifier.calendar_bot_token,
                        type="password",
                        placeholder="Optional: Leave empty to use the same bot as News..."
                    )
                    adm_cal_chat = gr.Textbox(
                        label="Calendar Group / Channel Chat ID",
                        value=telegram_notifier.calendar_chat_id,
                        placeholder="e.g. @my_calendar_channel or -1009876543210"
                    )
                    adm_cal_enabled = gr.Checkbox(
                        label="Enable Market Calendar & Outcomes Telegram Forwarding",
                        value=telegram_notifier.calendar_enabled
                    )
                    gr.Markdown("**⏰ Automated Daily Morning Dispatches (IST):**")
                    adm_auto_today_7am = gr.Checkbox(
                        label="🌅 07:00 AM IST — Auto-Forward Today's Complete Calendar & Timer Snapshot (5 Separate Msgs: NSE, BSE, MCX, Crypto, NYSE)",
                        value=telegram_notifier.auto_daily_today_7am
                    )
                    adm_auto_tom_705am = gr.Checkbox(
                        label="🌄 07:05 AM IST — Auto-Forward Tomorrow's Lined-Up Events Snapshot (5 Separate Msgs: NSE, BSE, MCX, Crypto, NYSE)",
                        value=telegram_notifier.auto_daily_tomorrow_705am
                    )
                    adm_auto_hol_7am = gr.Checkbox(
                        label="🏖️ 07:00 AM IST — Auto-Forward Next-Day Trading Holiday Alert (1 Day Before NSE/BSE/MCX/NYSE Holiday)",
                        value=telegram_notifier.auto_holiday_7am
                    )
                    adm_auto_weekly_fri7am = gr.Checkbox(
                        label="🗓️ Friday 07:00 AM IST — Auto-Forward Complete Upcoming Week Calendar Link (Apple & Google)",
                        value=getattr(telegram_notifier, "auto_weekly_fri_7am", False)
                    )
                    adm_auto_circulars = gr.Checkbox(
                        label="📜 Auto-Forward Critical Regulatory Circulars (NSE, BSE, MCX, RBI, FinMin, FOMC, NYSE, Crypto) with 3-5 Bullets & PDF Link",
                        value=getattr(telegram_notifier, "auto_circulars_tg", False)
                    )
                    adm_send_as_photos = gr.Checkbox(
                        label="📸 Deliver Morning Calendar Snapshots as Infographic Photo Cards (Details rendered directly in image)",
                        value=getattr(telegram_notifier, "send_as_photos", True)
                    )
                    adm_public_app_url = gr.Textbox(
                        label="Public Web Portal / API URL (Used for Apple & Google Calendar 1-Click Sync Links)",
                        value=telegram_notifier.public_app_url,
                        placeholder="e.g. https://news-engine-service.onrender.com or your custom domain"
                    )
                    gr.Markdown("**⚡ Real-Time Individual Event Triggers:**")
                    with gr.Row():
                        adm_cal_countdown = gr.Checkbox(label="⏰ T-15m Countdown Alerts", value=telegram_notifier.alert_on_countdown)
                        adm_cal_outcome = gr.Checkbox(label="🏁 Unfolded Outcome Alerts", value=telegram_notifier.alert_on_outcome)
                        adm_cal_linked = gr.Checkbox(label="🔗 Linked News Results", value=telegram_notifier.alert_on_linked_news)
                    
                    with gr.Row():
                        test_cal_tg_btn = gr.Button("🔔 Send Test Alert to Calendar Channel")
                        resend_weekly_btn = gr.Button("📲 Resend Full-Week Calendar Sync Link (Apple & Google) Now")

            save_adm_tg_btn = gr.Button("💾 Save All Telegram & Schedule Settings", variant="primary")
            adm_tg_status = gr.Markdown()

            save_adm_tg_btn.click(
                save_admin_telegram_settings,
                inputs=[
                    adm_news_token, adm_news_chat, adm_news_enabled,
                    adm_cal_token, adm_cal_chat, adm_cal_enabled,
                    adm_cal_countdown, adm_cal_outcome, adm_cal_linked,
                    adm_auto_today_7am, adm_auto_tom_705am, adm_auto_hol_7am,
                    adm_send_as_photos, adm_public_app_url, adm_auto_weekly_fri7am,
                    adm_auto_circulars
                ],
                outputs=[adm_tg_status]
            )
            test_news_tg_btn.click(lambda: trigger_test_telegram("news"), outputs=[adm_tg_status])
            test_cal_tg_btn.click(lambda: trigger_test_telegram("calendar"), outputs=[adm_tg_status])
            resend_weekly_btn.click(push_weekly_calendar_dispatch, outputs=[adm_tg_status])

            gr.Markdown("---")
            gr.Markdown("### 📅 Google Calendar Direct API Integration (Automated 1-Hour Reminder Alarms)")
            gr.Markdown(
                "Directly synchronizes events from the EPM Pro calendar into your personal or team Google Calendar with **60-minute email and popup reminders**. "
                "You can authenticate using a Google Cloud Service Account JSON key or JSON string."
            )
            with gr.Row():
                with gr.Column():
                    adm_gcal_id = gr.Textbox(
                        label="Google Calendar ID",
                        value=google_calendar_manager.calendar_id,
                        placeholder="e.g. primary or your-calendar-id@group.calendar.google.com"
                    )
                    adm_gcal_enabled = gr.Checkbox(
                        label="Enable Direct Google Calendar Sync",
                        value=google_calendar_manager.enabled
                    )
                with gr.Column():
                    adm_gcal_sa_file = gr.Textbox(
                        label="Service Account JSON File Path",
                        value=google_calendar_manager.service_account_file,
                        placeholder="e.g. service_account.json"
                    )
                    adm_gcal_sa_json = gr.Textbox(
                        label="Service Account JSON String (Optional, for Cloud / Docker)",
                        value=google_calendar_manager.service_account_json_str,
                        type="password",
                        placeholder='Paste full {"type": "service_account", ...} JSON'
                    )

            with gr.Row():
                save_gcal_btn = gr.Button("💾 Save Google Calendar Settings", variant="primary")
                sync_gcal_admin_btn = gr.Button("🔄 Sync All Active Events Now to Google Calendar (1h Alert)")

            gcal_admin_status = gr.Markdown()
            save_gcal_btn.click(
                save_google_calendar_settings,
                inputs=[adm_gcal_id, adm_gcal_sa_json, adm_gcal_sa_file, adm_gcal_enabled],
                outputs=[gcal_admin_status]
            )
            sync_gcal_admin_btn.click(trigger_sync_google_cal, outputs=[gcal_admin_status])

            gr.Markdown("---")
            gr.Markdown("### 📡 Connected News Sources & Selective Forwarding Rules")
            sources_table = gr.Dataframe(
                headers=["Source Name", "Category", "Ingestion Type", "Telegram Alerts", "WhatsApp Alerts", "Feed / Scrape URL"],
                datatype=["str", "str", "str", "str", "str", "str"],
                value=get_sources_table(),
                interactive=False,
                wrap=True,
                elem_id="sources_table"
            )

            min_score_slider = gr.Slider(
                minimum=0, maximum=10, value=news_worker.min_forward_score, step=1,
                label="Minimum AI Score Threshold for News (0 = Forward All News, 7 = High Impact Only)"
            )

            with gr.Row():
                with gr.Column():
                    tg_checkboxes = gr.CheckboxGroup(choices=all_source_names, value=default_tg_selected, label="✈️ Select News Channels for Telegram")
                with gr.Column():
                    wa_checkboxes = gr.CheckboxGroup(choices=all_source_names, value=default_wa_selected, label="💬 Select News Channels for WhatsApp")

            save_rules_btn = gr.Button("💾 Save Source Forwarding Rules", variant="primary")
            rules_status = gr.Markdown()

            save_rules_btn.click(
                save_forwarding_rules,
                inputs=[tg_checkboxes, wa_checkboxes, min_score_slider],
                outputs=[rules_status, sources_table]
            )

        # ═══════════════════════════════════════════════════════════
        # TAB 5: User Guide & Operations Manual (Dedicated Help Hub)
        # ═══════════════════════════════════════════════════════════
        with gr.TabItem("❓ User Guide & Operations Manual"):
            gr.HTML("""
            <div class="guide-container">
                <div class="guide-card">
                    <h3><span>🌅</span> Automated Morning Telegram Dispatches (IST Schedule)</h3>
                    <ul class="guide-list">
                        <li><span class="guide-pill">07:00 AM IST Daily</span> &nbsp;—&nbsp; Automatically forwards <b>Today's Complete Multi-Market Calendar snapshot</b> as <b>5 separate messages</b> (<span class="guide-badge">NSE</span>, <span class="guide-badge">BSE</span>, <span class="guide-badge">MCX</span>, <span class="guide-badge">CRYPTO</span>, <span class="guide-badge">NYSE</span>) directly into the designated Calendar channel, complete with countdown timers, previous consensus figures, and 1-click Google Calendar links.</li>
                        <li><span class="guide-pill">07:00 AM IST Daily (Holiday Check)</span> &nbsp;—&nbsp; Evaluates upcoming calendar schedules 24 hours in advance and auto-forwards a <b>Next-Day Trading Holiday Alert</b> across all 5 major bourses whenever a session closure or evening trading break is detected.</li>
                        <li><span class="guide-pill">07:05 AM IST Daily</span> &nbsp;—&nbsp; Automatically forwards <b>Tomorrow's Lined-Up Events snapshot</b> as 5 separate market messages, giving portfolio managers early visibility into upcoming catalysts.</li>
                        <li><span class="guide-pill">Friday 07:00 AM IST</span> &nbsp;—&nbsp; Forwards the universal 1-click <b>Weekly Calendar Sync Links</b> (Apple Calendar `.ics` & Google Calendar) to sync the entire following week with one tap.</li>
                    </ul>
                </div>

                <div class="guide-card">
                    <h3><span>⚡</span> Real-Time Unfolding Outcomes & Timer Triggers</h3>
                    <ul class="guide-list">
                        <li><b>T-15m Live Countdown Alerts:</b> Automatically notifies traders 15 minutes before high-impact economic releases (e.g. US CPI, RBI MPC Rate Decisions, Non-Farm Payrolls) to prepare for intraday volatility.</li>
                        <li><b>Live Outcome Dispatches:</b> When official figures unfold, the engine immediately calculates <span class="guide-pill">Actual vs Forecast vs Previous</span> and computes the institutional market verdict (<span style="color:#16a34a; font-weight:700;">🟢 BULLISH</span>, <span style="color:#dc2626; font-weight:700;">🔴 BEARISH</span>, or <span style="color:#475569; font-weight:700;">⚪ NEUTRAL</span>).</li>
                        <li><b>Linked Wire Intelligence:</b> As soon as breaking news hits the wire covering a scheduled catalyst (e.g. Reliance Q2 earnings report), the event row automatically binds a direct link to the verified article.</li>
                    </ul>
                </div>

                <div class="guide-card">
                    <h3><span>🌐</span> Multi-Market Institutional Coverage</h3>
                    <ul class="guide-list">
                        <li><b>🇮🇳 NSE & BSE:</b> Nifty 50 constituents, Bank Nifty, quarterly earnings releases, board meetings, dividend ex-dates, and F&O contract expiries.</li>
                        <li><b>⛽ MCX:</b> Crude Oil inventories, Natural Gas storage releases, Gold & Silver delivery contracts, and morning/evening trading session schedules.</li>
                        <li><b>₿ CRYPTO:</b> Bitcoin halving schedules, ETF net flow disclosures, protocol upgrades, and key macroeconomic digital asset triggers.</li>
                        <li><b>🇺🇸 NYSE & NASDAQ:</b> Federal Reserve FOMC interest rate meetings, Jackson Hole speeches, US CPI/PPI inflation prints, and US corporate mega-cap earnings.</li>
                    </ul>
                </div>

                <div class="guide-card">
                    <h3><span>📜</span> Authentic Document-Backed Regulatory Circulars</h3>
                    <ul class="guide-list">
                        <li><b>Verified Ingestion:</b> Continuously polls official repositories: <span class="guide-badge">NSE</span>, <span class="guide-badge">BSE</span>, <span class="guide-badge">MCX</span>, <span class="guide-badge">RBI</span>, <span class="guide-badge">FINMIN</span>, <span class="guide-badge">FOMC</span>, <span class="guide-badge">NYSE</span>, and <span class="guide-badge">CRYPTO</span>.</li>
                        <li><b>AI Executive Summaries (3-5 Bullets):</b> Distills legal and regulatory jargon into crisp, actionable directives covering margin requirements, circuit filter revisions, and operational compliance.</li>
                        <li><b>Native PDF Direct Access:</b> Every release features a verified 1-click link directly to the official PDF file stored in authentic regulator archives.</li>
                    </ul>
                </div>

                <div class="guide-card">
                    <h3><span>🧠</span> AI Impact & Sentiment Engine (Gemini 2.5 Architecture)</h3>
                    <ul class="guide-list">
                        <li><b>0-10 Impact Rating:</b> News items scored ≥ 7 or categorized as High Impact are automatically promoted to the Primary Wire table and eligible for instant Telegram push alerts.</li>
                        <li><b>Directional Verdict:</b> Analyzes the macro implications of breaking headlines to classify market sentiment into Bullish, Bearish, or Neutral.</li>
                        <li><b>Sector & Ticker Tagging:</b> Maps news events directly to impacted industrial sectors (e.g., Banking, Auto, IT, Energy, Commodities) and primary stock tickers.</li>
                    </ul>
                </div>

                <div class="guide-card">
                    <h3><span>📲</span> Calendar Subscriptions & 1-Click Sync</h3>
                    <ul class="guide-list">
                        <li><b>Universal iCal Subscription Feed:</b> Connect your Apple Calendar, Outlook, or Thunderbird using the dynamic subscription endpoint: <span class="guide-pill">/api/calendar/ics</span>. All 5 markets update automatically.</li>
                        <li><b>Google Calendar Direct Sync:</b> One-click sync buttons in the terminal and on event rows instantly create calendar events with automated <b>60-minute alarm notifications</b>.</li>
                        <li><b>Service Account Background Daemon:</b> For enterprise teams, configure Google Cloud Service Account credentials in Tab 4 for continuous headless sync.</li>
                    </ul>
                </div>

                <div class="guide-card">
                    <h3><span>📊</span> High-Density Institutional Table Navigation (2-Row Clamp)</h3>
                    <ul class="guide-list">
                        <li><b>Max 2-Row Line Clamping:</b> All table cells strictly clamp long headlines, event titles, and AI summaries to at most 2 rows with clean ellipsis (<span class="guide-pill">-webkit-line-clamp: 2</span>). This increases visible screen information density by <b>75%</b> and eliminates excessive vertical scrolling.</li>
                        <li><b>Structured Companion Columns:</b> Complementary attributes (Score, Sentiment, Tickers, AI Reasoning, Source, Timestamps) are placed side-by-side in dedicated columns.</li>
                        <li><b>Alternative Expanded Card Views:</b> When you wish to read entire paragraphs or explore full cards, toggle the <span class="guide-pill">🎴 Visual Feed</span> accordion available in each tab.</li>
                    </ul>
                </div>

                <div class="guide-card">
                    <h3><span>⚡</span> REST API & Developer Integration Reference</h3>
                    <ul class="guide-list">
                        <li><span class="guide-pill">GET /api/news</span> &nbsp;—&nbsp; Returns high-speed cached news items with AI scores, sector tags, and relevance ratings.</li>
                        <li><span class="guide-pill">GET /api/calendar</span> &nbsp;—&nbsp; Returns enriched multi-market events, live timers, and unfolded outcomes.</li>
                        <li><span class="guide-pill">GET /api/calendar/ics</span> &nbsp;—&nbsp; RFC 5545 compliant iCalendar feed compatible with Apple, Google, and Microsoft platforms.</li>
                        <li><span class="guide-pill">GET /api/circulars</span> &nbsp;—&nbsp; Indexed regulatory circulars, AI 3-5 bullet points, and verified PDF links.</li>
                        <li><span class="guide-pill">GET /docs</span> &nbsp;—&nbsp; Complete OpenAPI / Swagger interactive documentation and API sandbox.</li>
                    </ul>
                </div>
            </div>
            """)

    refresh_btn.click(manual_refresh, outputs=[status_box, top_news_visual, top_table, bottom_table]).then(None, js="() => window.epmPlayChime(false)")
    demo.load(get_dashboard_tables, outputs=[status_box, top_news_visual, top_table, bottom_table])
    demo.load(get_calendar_tables, inputs=[cal_filter, cal_market_filter], outputs=[cal_info_bar, calendar_visual_feed, calendar_table, holidays_table])
    demo.load(get_circulars_view, inputs=[circ_reg_filter, circ_imp_filter, circ_search], outputs=[circ_info_bar, circ_visual_feed, circ_table])

# Mount Gradio UI inside FastAPI with full-width responsive CSS and Terminal Engine JS
app = gr.mount_gradio_app(
    app,
    demo,
    path="/",
    theme=gr.themes.Soft(),
    css=CUSTOM_CSS,
    head=f"<style>{CUSTOM_CSS}</style><script>{TERMINAL_CLIENT_JS}</script>",
    js=TERMINAL_CLIENT_JS
)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
