import os
import time
import html
import re
import sqlite3
import json
from typing import Optional, List, Dict
from datetime import datetime
from fastapi import FastAPI, Query, BackgroundTasks, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import asyncio
import gradio as gr

load_dotenv()

from news_worker import news_worker
from ai_analyzer import ai_analyzer
from telegram_notifier import telegram_notifier
from whatsapp_notifier import whatsapp_notifier
from calendar_engine import calendar_engine, now_ist, MARKETS_ORDER, MARKET_META
from google_calendar_manager import google_calendar_manager
from circular_engine import circular_engine, REGULATORS, REGULATOR_META
from social_publisher import social_publisher, MEDIA_DIR
from news_card_generator import news_card_generator
from calendar_pdf_engine import calendar_pdf_engine

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


@app.get("/api/media/{filename}")
async def serve_media(filename: str):
    """Serves high-contrast 1080x1350 financial infographic cards for Instagram Meta Graph API and external social networks."""
    safe_fn = os.path.basename(filename)
    path = os.path.join(MEDIA_DIR, safe_fn)
    if os.path.exists(path):
        return FileResponse(path, media_type="image/png")
    return PlainTextResponse("Media card not found", status_code=404)


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
    auto_daily_today_7am: Optional[bool] = False
    auto_daily_tomorrow_705am: Optional[bool] = False
    auto_holiday_7am: Optional[bool] = True
    auto_weekly_pdf_fri_6am: Optional[bool] = True
    auto_monthly_pdf_25th_6am: Optional[bool] = True


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


@app.get("/health/live")
def health_liveness():
    """Kubernetes & container liveness probe: verifies worker loop is actively pulsing."""
    now_ts = time.time()
    wb_heartbeat = getattr(news_worker, "last_heartbeat", now_ts)
    drift = now_ts - wb_heartbeat
    if drift > 300.0:
        raise HTTPException(status_code=503, detail=f"News worker heartbeat stalled: {drift:.1f}s drift")
    return {
        "status": "alive",
        "worker_heartbeat_drift_sec": round(drift, 2),
        "timestamp": now_ist().isoformat()
    }


@app.get("/health/ready")
def health_readiness():
    """Readiness probe: checks if essential feeds and calendars are populated."""
    has_news = len(news_worker.news_cache) > 0 or news_worker.is_initialized
    has_cal = len(calendar_engine.events) > 0
    return {
        "status": "ready" if (has_news or has_cal) else "warming_up",
        "cached_news": len(news_worker.news_cache),
        "calendar_events": len(calendar_engine.events),
        "timestamp": now_ist().isoformat()
    }


@app.get("/api/stream/terminal")
async def terminal_sse_stream():
    """Fast Server-Sent Events stream delivering real-time telemetry and sub-50ms delta updates."""
    async def event_generator():
        last_news_count = -1
        last_cal_count = -1
        while True:
            try:
                curr_news_count = len(news_worker.news_cache)
                curr_cal_count = len(calendar_engine.events)
                
                if curr_news_count != last_news_count or curr_cal_count != last_cal_count:
                    last_news_count = curr_news_count
                    last_cal_count = curr_cal_count
                    latest_item = news_worker.news_cache[0] if news_worker.news_cache else None
                    payload = {
                        "type": "telemetry",
                        "news_count": curr_news_count,
                        "cal_count": curr_cal_count,
                        "circ_count": len(getattr(circular_engine, "circulars_cache", [])) or 23,
                        "timestamp": now_ist().strftime("%H:%M:%S IST"),
                        "latest_title": latest_item.get("title", "") if latest_item else ""
                    }
                    yield f"event: telemetry\ndata: {json.dumps(payload)}\n\n"
                else:
                    yield ": ping\n\n"
                
                await asyncio.sleep(3.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                yield f": error {str(e)}\n\n"
                await asyncio.sleep(5.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


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


@app.get("/api/calendar/pdf/weekly")
def download_weekly_pdf_endpoint():
    """Generates and downloads the A4 Landscape Weekly Snapshot PDF (Next Mon-Sat) for 1-click download."""
    pdf_path = calendar_pdf_engine.generate_and_save_weekly_pdf()
    fn = os.path.basename(pdf_path)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=fn,
        headers={"Content-Disposition": f'attachment; filename="{fn}"'}
    )


@app.get("/api/calendar/pdf/monthly")
def download_monthly_pdf_endpoint():
    """Generates and downloads the A4 Landscape Monthly Outlook PDF (Upcoming Month) for 1-click download."""
    pdf_path = calendar_pdf_engine.generate_and_save_monthly_pdf()
    fn = os.path.basename(pdf_path)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=fn,
        headers={"Content-Disposition": f'attachment; filename="{fn}"'}
    )


@app.get("/api/calendar/pdf/daily-outcomes")
def download_daily_outcomes_pdf_endpoint():
    """Generates and downloads the A4 Landscape Daily Outcomes PDF (Yesterday 5 PM to Today 5 PM) for 1-click download."""
    pdf_path = calendar_pdf_engine.generate_and_save_daily_outcomes_pdf()
    fn = os.path.basename(pdf_path)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=fn,
        headers={"Content-Disposition": f'attachment; filename="{fn}"'}
    )


@app.post("/api/calendar/dispatch/weekly-pdf")
def api_dispatch_weekly_pdf():
    """Dispatches the A4 Landscape Weekly Snapshot PDF directly to the Telegram Calendar channel."""
    ok, msg = calendar_engine.dispatch_weekly_pdf_dossier()
    return {"status": "success" if ok else "error", "detail": msg}


@app.post("/api/calendar/dispatch/monthly-pdf")
def api_dispatch_monthly_pdf():
    """Dispatches the A4 Landscape Monthly Outlook PDF directly to the Telegram Calendar channel."""
    ok, msg = calendar_engine.dispatch_monthly_pdf_dossier()
    return {"status": "success" if ok else "error", "detail": msg}


@app.post("/api/calendar/dispatch/daily-outcomes-pdf")
def api_dispatch_daily_outcomes_pdf():
    """Dispatches the Daily Outcomes PDF directly to the Telegram Calendar channel."""
    ok, msg = calendar_engine.dispatch_daily_outcomes_pdf_dossier()
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
        "auto_weekly_pdf_fri_6am": telegram_notifier.auto_weekly_pdf_fri_6am,
        "auto_monthly_pdf_25th_6am": telegram_notifier.auto_monthly_pdf_25th_6am,
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
        auto_holiday_7am=bool(cfg.auto_holiday_7am),
        auto_weekly_pdf_fri_6am=bool(cfg.auto_weekly_pdf_fri_6am),
        auto_monthly_pdf_25th_6am=bool(cfg.auto_monthly_pdf_25th_6am)
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
        doc_url = html.escape(str(c.get("pdf_url") or c.get("web_url") or "").strip())
        category = html.escape(str(c.get("category", "Regulatory Disclosure")))
        impact = str(c.get("impact", "MEDIUM")).upper()
        bullets = c.get("bullets", [])
        action = html.escape(str(c.get("action_takeaway", "")))

        is_high = impact == "HIGH"
        impact_badge = f'<span class="epm-badge impact-{"high" if is_high else "medium"}">{"🚨 CRITICAL IMPACT" if is_high else "📌 OFFICIAL DIRECTIVE"}</span>'

        bullet_items = "".join(f'<li>{html.escape(str(b))}</li>' for b in bullets) if bullets else f'<li>{title}</li>'
        pdf_btn_html = f'<a href="{doc_url}" target="_blank" rel="noopener noreferrer" class="epm-pdf-btn">📥 Download Official Document ↗</a>' if doc_url else '<span class="epm-pdf-btn-disabled">📄 In Repository</span>'
        title_html = f'<a href="{doc_url}" target="_blank" rel="noopener noreferrer" class="epm-circ-title-link">{title}</a>' if doc_url else f'<span class="epm-circ-title">{title}</span>'

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
                    {pdf_btn_html}
                </div>
            </div>
            <div class="epm-card-body">
                <div class="epm-circ-title-row">
                    {title_html}
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
        search_str = "" if search_query is None else str(search_query).strip()
        reg_filter = "ALL" if regulator_filter is None else str(regulator_filter).strip()
        imp_filter = "ALL" if impact_filter is None else str(impact_filter).strip()

        items = circular_engine.get_circulars(
            regulator_filter=reg_filter,
            impact_filter=imp_filter,
            search_query=search_str
        )
        visual_html = render_circulars_feed_html(items)
        
        table_rows = []
        for it in items:
            meta = REGULATOR_META.get(it.get("regulator", "NSE"), {"badge": it.get("regulator", "NSE")})
            pdf_link = str(it.get("pdf_url") or it.get("web_url") or "").strip()
            if pdf_link:
                pdf_display = f"[📥 Download PDF ↗]({pdf_link})"
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
            f"🏛️ **Authority Filter:** `{reg_filter}` &nbsp;|&nbsp; "
            f"🚨 **Impact Filter:** `{imp_filter}` &nbsp;|&nbsp; "
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
                    impact=row["impact"],
                    bullets=bullets,
                    action_takeaway=row["action_takeaway"]
                )
                ok, err = telegram_notifier.send_calendar_digest(msg)
                if ok:
                    conn.execute("UPDATE circulars SET dispatched_tg = 1 WHERE id = ?", (row["id"],))
                    conn.commit()
                    return f"✅ **Dispatched Official [{row['regulator']}] Circular `{row['circular_no']}` with 3-5 Bullets & PDF Download Link to Telegram!**"
                return f"⚠️ **Telegram Dispatch Notice:** {err} *(Verify Telegram settings in Tab 4)*"
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


def render_calendar_dossier_html(events: List[Dict]) -> str:
    """
    Renders an exact, interactive high-fidelity replica of the ReportLab A4 PDF Dossier
    directly on the web page. Groups catalysts date-by-date with warm gold section banners,
    faint amber table headers, alternating zebra striping, and distinct color-coded badges.
    """
    if not events:
        return (
            '<div class="epm-empty-state">'
            '  <div class="epm-empty-icon">📅</div>'
            '  <div class="epm-empty-title">No Scheduled Catalysts Found For This Filter</div>'
            '  <div class="epm-empty-sub">Switch the market or time window filter above to explore scheduled corporate releases.</div>'
            '</div>'
        )

    events_by_date: Dict[str, List[Dict]] = {}
    for ev in events:
        d = ev.get("date", "")
        if not d:
            continue
        if d not in events_by_date:
            events_by_date[d] = []
        events_by_date[d].append(ev)

    sorted_dates = sorted(events_by_date.keys())
    global_row_idx = 1
    all_table_rows = []
    rendered_total = 0
    max_render = 300

    for date_str in sorted_dates:
        if rendered_total >= max_render:
            break
        day_events = events_by_date[date_str]
        day_events.sort(key=lambda x: (str(x.get("time", "99:99")), calendar_pdf_engine._classify_event_type(x)))

        try:
            dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
            day_name_full = dt_obj.strftime("%A")
            formatted_date = dt_obj.strftime("%d %B %Y").upper()
            day_name_short = dt_obj.strftime("%a")
        except Exception:
            day_name_full = "—"
            formatted_date = date_str
            day_name_short = "—"

        # Ultra-sleek Sticky Day Group Ribbon
        ribbon_row = f"""
        <tr class="epm-day-ribbon-row" data-date="{html.escape(date_str)}">
            <td colspan="15">
                <div class="epm-day-ribbon-content">
                    <div class="epm-ribbon-left">
                        <span class="epm-ribbon-bullet">●</span>
                        <span class="epm-ribbon-date">{html.escape(formatted_date)}</span>
                        <span class="epm-ribbon-day">{html.escape(day_name_full)}</span>
                    </div>
                    <div class="epm-ribbon-right">
                        <span class="epm-ribbon-tally">{len(day_events)} CATALYSTS SCHEDULED</span>
                    </div>
                </div>
            </td>
        </tr>
        """
        all_table_rows.append(ribbon_row)

        for r_i, ev in enumerate(day_events):
            if rendered_total >= max_render:
                break
            ev_type = calendar_pdf_engine._classify_event_type(ev)
            t_str = calendar_pdf_engine._format_event_time(ev)
            country, regulator = calendar_pdf_engine._infer_country_and_regulator(ev)
            sector = calendar_pdf_engine._infer_sector(ev)
            impact_stars = calendar_pdf_engine._infer_impact_stars(ev)

            # Format Date as DD-MM-YYYY instead of YYYY-MM-DD
            d_parts = date_str.split("-")
            formatted_date_cell = f"{d_parts[2]}-{d_parts[1]}-{d_parts[0]}" if len(d_parts) == 3 else date_str

            raw_ev_name = clean_table_text(ev.get("event", "Scheduled Release"))
            if ev.get("symbol") and ev.get("symbol") not in raw_ev_name:
                clean_sym = clean_table_text(str(ev.get("symbol", "")).replace("NSE:", "").replace("BSE:", "").replace("MCX:", ""))
                if clean_sym:
                    raw_ev_name = f"{clean_sym} — {raw_ev_name}"

            prev_val = clean_table_text(str(ev.get("previous", "—")) or "—")
            fore_val = clean_table_text(str(ev.get("forecast", "—")) or "—")
            actual_val = clean_table_text(str(ev.get("actual", "⏳ Pending")) or "⏳ Pending")
            if not actual_val or actual_val in ("—", "None"):
                actual_val = "⏳ Pending"
            is_outcome_released = not actual_val.startswith("⏳") and actual_val != "Scheduled"
            outcome_class = "outcome-released" if is_outcome_released else "outcome-pending"
            outcome_badge = f'<span class="epm-outcome-pill {outcome_class}" title="{html.escape(actual_val)}">{html.escape(actual_val)}</span>'

            sent_text, _ = calendar_pdf_engine._format_sentiment(ev)
            reasoning = clean_table_text(calendar_pdf_engine._build_ai_reasoning(ev))

            badge_class = "badge-general"
            if ev_type == "Earning Cal.":
                badge_class = "badge-earnings"
            elif ev_type == "Econ Cal.":
                badge_class = "badge-econ"
            elif ev_type == "Holiday":
                badge_class = "badge-holiday"
            elif ev_type == "Special Session":
                badge_class = "badge-special"
            elif "Corp." in ev_type:
                badge_class = "badge-corp"

            sent_class = "sent-neutral"
            if "Bull" in sent_text:
                sent_class = "sent-bullish"
            elif "Bear" in sent_text:
                sent_class = "sent-bearish"

            row_bg = "epm-dossier-row-even" if (r_i % 2 == 0) else "epm-dossier-row-odd"

            star_count = impact_stars.count("★") if "★" in impact_stars else impact_stars.count("*")
            if star_count == 0:
                star_count = 3
            level_label = {5: "CRITICAL", 4: "HIGH", 3: "MEDIUM", 2: "LOW", 1: "MINOR"}.get(star_count, "STANDARD")
            pip_tier_class = f"tier-{star_count}"
            pips_html = "".join(f'<span class="pip {"on" if i < star_count else ""}"></span>' for i in range(5))
            # Minimalist self-sufficient graded bars without text clutter
            pip_badge = f'<div class="epm-signal-pips {pip_tier_class}" title="Impact Level: {star_count}/5 ({level_label})">{pips_html}</div>'

            all_table_rows.append(f"""
            <tr class="epm-dossier-row {row_bg}">
                <td class="col-idx">{global_row_idx}</td>
                <td class="col-date">{html.escape(formatted_date_cell)}</td>
                <td class="col-time">{html.escape(t_str)}</td>
                <td class="col-day">{html.escape(day_name_short)}</td>
                <td class="col-type"><span class="epm-dossier-badge {badge_class}">{html.escape(ev_type)}</span></td>
                <td class="col-country">{html.escape(country)}</td>
                <td class="col-reg">{html.escape(regulator)}</td>
                <td class="col-sec">{html.escape(sector)}</td>
                <td class="col-event"><b>{html.escape(raw_ev_name)}</b></td>
                <td class="col-imp">{pip_badge}</td>
                <td class="col-num">{html.escape(prev_val)}</td>
                <td class="col-num col-fore">{html.escape(fore_val)}</td>
                <td class="col-outcome">{outcome_badge}</td>
                <td class="col-sent"><span class="epm-sent-badge {sent_class}">● {html.escape(sent_text.upper())}</span></td>
                <td class="col-reason">{html.escape(reasoning)}</td>
            </tr>
            """)
            global_row_idx += 1
            rendered_total += 1

    footer_note = ""
    if len(events) > max_render:
        footer_note = f"""
        <div class="epm-dossier-footer-note">
            <span>Displaying first {rendered_total} of {len(events)} catalysts for this horizon. Filter by timeframe or market above for focused schedules, or click <b>Download Weekly / Monthly Snapshot PDF</b> for the complete ledger archive.</span>
        </div>
        """

    return f"""
    <div class="epm-dossier-container">
        <div class="epm-dossier-table-wrap">
            <table class="epm-dossier-table">
                <thead>
                    <tr>
                        <th class="col-idx">#</th>
                        <th class="col-date">Date</th>
                        <th class="col-time">Time (IST)</th>
                        <th class="col-day">Day</th>
                        <th class="col-type">Type</th>
                        <th class="col-country">Country</th>
                        <th class="col-reg">Reg.</th>
                        <th class="col-sec">Sector</th>
                        <th class="col-event">Event Catalyst</th>
                        <th class="col-imp">Impact</th>
                        <th class="col-num">Previous</th>
                        <th class="col-num">Forecast</th>
                        <th class="col-outcome">Results</th>
                        <th class="col-sent">Sentiment</th>
                        <th class="col-reason">AI Quantitative Reasoning</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(all_table_rows)}
                </tbody>
            </table>
        </div>
        <a href="/api/calendar/pdf/daily-outcomes" download target="_blank" class="epm-daily-pdf-floater" title="Download Official 5 PM Daily Outcomes Dossier (Rolling 24H Results)">
            <span class="floater-pulse"></span>
            <span class="floater-label">📥 <b>Daily Outcomes PDF (5 PM Release)</b></span>
            <span class="floater-tag">A4 Dossier</span>
        </a>
        {footer_note}
    </div>
    """


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
        calendar_visual_html = render_calendar_dossier_html(events)
        cal_rows = []
        global_idx = 1
        for ev in events:
            ev_type = calendar_pdf_engine._classify_event_type(ev)
            country, regulator = calendar_pdf_engine._infer_country_and_regulator(ev)
            sector = calendar_pdf_engine._infer_sector(ev)
            impact_stars = calendar_pdf_engine._infer_impact_stars(ev)
            t_str = calendar_pdf_engine._format_event_time(ev)

            d_str = str(ev.get("date", ""))
            d_parts = d_str.split("-")
            formatted_d = f"{d_parts[2]}-{d_parts[1]}-{d_parts[0]}" if len(d_parts) == 3 else d_str
            try:
                dt_obj = datetime.strptime(d_str, "%Y-%m-%d")
                day_name = dt_obj.strftime("%a")
            except Exception:
                day_name = "—"

            raw_ev_name = clean_table_text(ev.get("event", "Scheduled Release"))
            if ev.get("symbol") and ev.get("symbol") not in raw_ev_name:
                clean_sym = clean_table_text(str(ev.get("symbol", "")).replace("NSE:", "").replace("BSE:", "").replace("MCX:", ""))
                if clean_sym:
                    raw_ev_name = f"{clean_sym} — {raw_ev_name}"

            prev_val = clean_table_text(str(ev.get("previous", "—")) or "—")
            fore_val = clean_table_text(str(ev.get("forecast", "—")) or "—")
            actual_val = clean_table_text(str(ev.get("actual", "⏳ Pending")) or "⏳ Pending")
            sent_text, _ = calendar_pdf_engine._format_sentiment(ev)
            reasoning = calendar_pdf_engine._build_ai_reasoning(ev)

            cal_rows.append([
                str(global_idx),
                formatted_d,
                t_str,
                day_name,
                ev_type,
                country,
                regulator,
                sector,
                raw_ev_name,
                impact_stars,
                prev_val,
                fore_val,
                actual_val,
                sent_text,
                reasoning
            ])
            global_idx += 1

        if not cal_rows:
            cal_rows.append(["-", "-", "-", "-", "-", "-", "-", "-", "No events for selected market/time filter", "-", "-", "-", "-", "-", "-"])

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
        empty_cal = [["-", "-", "-", "-", "-", "-", "-", f"Calendar Notice: {str(e)}", "-", "-", "-", "-", "-", "-", "-"]]
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
    return f"⚠️ **Could not send Weekly Calendar Link:** {msg} *(Configure Calendar Telegram Chat ID in Tab 4)*"


def handle_download_weekly_pdf():
    pdf_path = calendar_pdf_engine.generate_and_save_weekly_pdf()
    fn = os.path.basename(pdf_path)
    return (
        f"✅ **Weekly Snapshot PDF Generated!** `{fn}` covering next week's Monday–Saturday across NSE, BSE, MCX, CRYPTO & NYSE.\n"
        f"Click the download file link below or access directly via `/api/calendar/pdf/weekly`.",
        gr.update(value=pdf_path, visible=True)
    )


def handle_download_monthly_pdf():
    pdf_path = calendar_pdf_engine.generate_and_save_monthly_pdf()
    fn = os.path.basename(pdf_path)
    return (
        f"✅ **Monthly Outlook PDF Generated!** `{fn}` covering the upcoming month sectioned weekly.\n"
        f"Click the download file link below or access directly via `/api/calendar/pdf/monthly`.",
        gr.update(value=pdf_path, visible=True)
    )


def handle_dispatch_weekly_pdf_telegram():
    ok, msg = calendar_engine.dispatch_weekly_pdf_dossier()
    pdf_path = calendar_pdf_engine.generate_and_save_weekly_pdf()
    fn = os.path.basename(pdf_path)
    if ok:
        return (
            f"✅ **Weekly Multi-Market A4 PDF dossier (`{fn}`) successfully dispatched to Telegram `{telegram_notifier.calendar_chat_id}`!**",
            gr.update(visible=False)
        )
    return f"⚠️ **Could not dispatch Weekly PDF to Telegram:** {msg}", gr.update(visible=False)


def handle_dispatch_monthly_pdf_telegram():
    ok, msg = calendar_engine.dispatch_monthly_pdf_dossier()
    pdf_path = calendar_pdf_engine.generate_and_save_monthly_pdf()
    fn = os.path.basename(pdf_path)
    if ok:
        return (
            f"✅ **Monthly Multi-Market A4 PDF outlook (`{fn}`) successfully dispatched to Telegram `{telegram_notifier.calendar_chat_id}`!**",
            gr.update(visible=False)
        )
    return f"⚠️ **Could not dispatch Monthly PDF to Telegram:** {msg}", gr.update(visible=False)


def handle_download_daily_outcomes_pdf():
    pdf_path = calendar_pdf_engine.generate_and_save_daily_outcomes_pdf()
    fn = os.path.basename(pdf_path)
    return (
        f"✅ **Daily Outcomes PDF Generated!** `{fn}` covering unfolded results & events from Yesterday 5 PM to Today 5 PM IST.\n"
        f"Click the download file link below or access directly via `/api/calendar/pdf/daily-outcomes`.",
        gr.update(value=pdf_path, visible=True)
    )


def handle_dispatch_daily_outcomes_pdf_telegram():
    ok, msg = calendar_engine.dispatch_daily_outcomes_pdf_dossier()
    pdf_path = calendar_pdf_engine.generate_and_save_daily_outcomes_pdf()
    fn = os.path.basename(pdf_path)
    if ok:
        return (
            f"✅ **Daily Outcomes A4 PDF dossier (`{fn}`) successfully dispatched to Telegram `{telegram_notifier.calendar_chat_id}`!**",
            gr.update(visible=False)
        )
    return f"⚠️ **Could not dispatch Daily Outcomes PDF to Telegram:** {msg}", gr.update(visible=False)


def handle_download_ics_file():
    events = calendar_engine.get_enriched_events(filter_range="all", market_filter="ALL")
    ics_content = google_calendar_manager.generate_enhanced_ics(events)
    ics_path = os.path.join(MEDIA_DIR, "epm_multi_market_calendar.ics")
    with open(ics_path, "w", encoding="utf-8") as f:
        f.write(ics_content)
    return "✅ **RFC 5545 iCalendar feed file generated!** Click to download below or subscribe via `/api/calendar/ics`.", gr.update(value=ics_path, visible=True)


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
    auto_circulars_tg: bool = False,
    auto_weekly_pdf_fri6am: bool = True,
    auto_monthly_pdf_25th6am: bool = True
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
        auto_circulars_tg=auto_circulars_tg,
        auto_weekly_pdf_fri_6am=auto_weekly_pdf_fri6am,
        auto_monthly_pdf_25th_6am=auto_monthly_pdf_25th6am
    )
    format_mode = "Infographic Photo Cards 📸" if send_photos else "Detailed Text Messages 💬"
    return (
        f"✅ **Admin Telegram & Automated Schedule Settings Saved!**\n"
        f"- **News Channel ID:** `{telegram_notifier.chat_id or 'Not Set'}` (Enabled: `{telegram_notifier.enabled}`)\n"
        f"- **Calendar Channel ID:** `{telegram_notifier.calendar_chat_id or 'Not Set'}` (Enabled: `{telegram_notifier.calendar_enabled}`)\n"
        f"- **Public Portal URL:** `{telegram_notifier.get_public_url()}`\n"
        f"- **Morning Dispatch Format:** `{format_mode}`\n"
        f"- **Automated Schedule (6:00 AM IST):** Friday 6 AM Weekly PDF=`{auto_weekly_pdf_fri6am}` | 25th 6 AM Monthly PDF=`{auto_monthly_pdf_25th6am}` | Pre-Holiday Alert 7 AM=`{auto_hol_7am}` | Legacy Today/Tomorrow Msg=`{auto_today_7am}`/`{auto_tom_705am}`"
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


def save_social_media_settings(
    ig_en: bool,
    ig_acc: str,
    ig_token: str,
    tw_en: bool,
    tw_key: str,
    tw_sec: str,
    tw_tok: str,
    tw_tsec: str,
    tw_min: int,
    dc_en: bool,
    dc_wh: str,
    news_photos: bool,
    pub_url: str
):
    social_publisher.save_settings(
        instagram_enabled=ig_en,
        instagram_account_id=ig_acc,
        instagram_access_token=ig_token,
        twitter_enabled=tw_en,
        twitter_api_key=tw_key,
        twitter_api_secret=tw_sec,
        twitter_access_token=tw_tok,
        twitter_access_secret=tw_tsec,
        twitter_min_score=tw_min,
        discord_enabled=dc_en,
        discord_webhook_url=dc_wh,
        send_news_as_photos=news_photos,
        public_app_url=pub_url
    )
    telegram_notifier.send_news_as_photos = news_photos
    ig_status = "🟢 Enabled" if ig_en else "⚪ Disabled"
    tw_status = "🟢 Enabled" if tw_en else "⚪ Disabled"
    dc_status = "🟢 Enabled" if dc_en else "⚪ Disabled"
    mode = "Graphic Infographic Cards 🖼️" if news_photos else "Plain Text 💬"
    return (
        f"✅ **Omnichannel Social Media Settings Saved!**\n\n"
        f"• **Instagram Meta Graph API:** {ig_status} (ID: `{ig_acc or 'None'}`)\n"
        f"• **X / Twitter API v2:** {tw_status} (Min Score: `{tw_min}/10`)\n"
        f"• **Discord Webhook:** {dc_status}\n"
        f"• **Visual Format:** `{mode}`\n"
        f"• **Public Image Server URL:** `{social_publisher.get_public_url()}`"
    )


def trigger_test_social(platform: str):
    sample = {
        "title": "RBI Unexpectedly Cuts Repo Rate by 25 bps; Injects Rs. 1.2 Lakh Cr Liquidity",
        "ai_score": 9,
        "ai_sentiment": "BULLISH",
        "ai_impact": "HIGH",
        "ai_sectors": ["Banking", "NBFC", "Auto", "Real Estate"],
        "ai_reasoning": "Off-cycle monetary easing to accelerate credit growth and expand banking net interest margins.",
        "source": "EPM Pro Institutional Wire",
        "timestamp": now_ist().strftime("%Y-%m-%d %H:%M IST")
    }
    card_bytes = news_card_generator.render_news_card(sample)
    if platform == "instagram":
        caption = social_publisher.format_social_caption(sample)
        ok, msg = social_publisher.post_to_instagram(card_bytes, caption)
        return f"📸 **Instagram Test Post:** {'✅ ' if ok else '❌ '} {msg}"
    elif platform == "twitter":
        text = social_publisher.format_twitter_text(sample)
        ok, msg = social_publisher.post_to_twitter(card_bytes, text)
        return f"🐦 **Twitter Test Tweet:** {'✅ ' if ok else '❌ '} {msg}"
    elif platform == "discord":
        desc = sample.get("ai_reasoning", "")
        ok, msg = social_publisher.post_to_discord(card_bytes, sample["title"], desc, 0x10b981)
        return f"🎮 **Discord Test Embed:** {'✅ ' if ok else '❌ '} {msg}"
    return "Unknown platform"


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


def render_section_controls(section_id: str, show_reorder: bool = True, show_collapse: bool = True) -> str:
    """Renders ultra-compact institutional Move Up / Move Down / Collapse controls."""
    reorder_html = ""
    if show_reorder:
        reorder_html = f"""
        <div class="epm-section-reorder-group" title="Reorder section (Move Up / Down)">
            <button type="button" class="epm-ribbon-btn epm-reorder-btn epm-move-up" onclick="window.epmMoveSection('{section_id}', 'up')" title="Move Section Up">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m18 15-6-6-6 6"/></svg>
            </button>
            <button type="button" class="epm-ribbon-btn epm-reorder-btn epm-move-down" onclick="window.epmMoveSection('{section_id}', 'down')" title="Move Section Down">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
            </button>
        </div>
        """

    collapse_html = ""
    if show_collapse:
        collapse_html = f"""
        <button type="button" class="epm-ribbon-btn epm-collapse-btn" onclick="window.epmToggleCollapse('{section_id}', this)" title="Collapse or Expand this section">
            <svg class="epm-chevron-icon" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
        </button>
        """

    return f"""
    <div class="epm-section-ctrl-wrap">
        {reorder_html}
        {collapse_html}
    </div>
    """


def render_table_ribbon(
    table_id: str,
    title: str,
    subtitle: str = "",
    count_badge: str = "",
    section_id: str = "",
    show_csv: bool = True,
    show_focus: bool = True,
    show_reorder: bool = True,
    show_collapse: bool = True,
) -> str:
    sec_id = section_id or f"sec_{table_id}"
    sub_badge = f'<span class="epm-ribbon-badge">{subtitle}</span>' if subtitle else ""
    cnt_badge = f'<span class="epm-ribbon-count" id="{table_id}_count">{count_badge}</span>' if count_badge else ""

    csv_btn = f"""
    <button type="button" class="epm-ribbon-btn" onclick="window.epmExportCSV('{table_id}')" title="Download table records as standard RFC-4180 CSV">
        📥 <span>CSV</span>
    </button>
    """ if show_csv else ""

    focus_btn = f"""
    <button type="button" class="epm-ribbon-btn" onclick="window.epmToggleFocus('{table_id}')" title="Full-Screen Focus Mode (Press ESC to exit)">
        ⛶ <span>Focus</span>
    </button>
    """ if show_focus else ""

    controls_html = render_section_controls(sec_id, show_reorder=show_reorder, show_collapse=show_collapse)

    return f"""
    <div class="epm-table-ribbon" data-target="{table_id}" data-section="{sec_id}">
        <div class="epm-ribbon-left">
            <span class="epm-ribbon-bullet">●</span>
            <span class="epm-ribbon-title">{title}</span>
            {sub_badge}
            {cnt_badge}
        </div>
        <div class="epm-ribbon-controls">
            {csv_btn}
            {focus_btn}
            {controls_html}
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

:root {
    --font-sans: -apple-system, BlinkMacSystemFont, "Inter", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    
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
    padding: 3px 16px 12px 16px !important;
    background-color: #ffffff !important;
    color: var(--text-primary) !important;
    overflow-x: hidden !important;
}

.gradio-container .tabs,
.gradio-container .tabitem,
.gradio-container .column,
.gradio-container .contain,
.gradio-container .main > .wrap > .contain {
    padding: 0 !important;
    margin: 0 !important;
    gap: 0 !important;
    border: none !important;
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
    margin-bottom: 6px !important;
}

table {
    table-layout: fixed !important;
    width: 100% !important;
    max-width: 100% !important;
    border-collapse: collapse !important;
    font-family: var(--font-sans) !important;
    background: #ffffff !important;
    font-feature-settings: "cv02", "cv03", "cv04", "cv11" !important;
}

thead th {
    background-color: #f8fafc !important;
    color: #475569 !important;
    font-family: var(--font-sans) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.02em !important;
    padding: 5px 8px !important;
    border-bottom: 1px solid #cbd5e1 !important;
    border-right: 1px solid #f1f5f9 !important;
    white-space: nowrap !important;
    vertical-align: middle !important;
    position: sticky !important;
    top: 0 !important;
    z-index: 2 !important;
}

tbody td {
    padding: 4px 8px !important;
    font-size: 11.5px !important;
    color: #0f172a !important;
    border-bottom: 1px solid #f1f5f9 !important;
    border-right: 1px solid #f8fafc !important;
    vertical-align: middle !important;
    line-height: 1.32 !important;
    word-break: break-word !important;
    overflow-wrap: anywhere !important;
    background: #ffffff !important;
    height: auto !important;
    font-family: var(--font-sans) !important;
}

tbody tr:nth-child(even) td {
    background-color: #fcfdfe !important;
}

tbody tr:hover td {
    background-color: #f8fafc !important;
}

/* 9. Monospace Elements for Raw Code / Hash Tokens Only */
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
#circ_table tbody td:nth-child(5) > *,
#circ_table tbody td:nth-child(5) a,
#circ_table tbody td:nth-child(7) > * {
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    max-height: 2.65em !important;
    line-height: 1.32 !important;
    word-break: break-word !important;
}

#top_news_table tbody td:nth-child(4),
#top_news_table tbody td:nth-child(5),
#top_news_table tbody td:nth-child(6),
#bottom_news_table tbody td:nth-child(3),
#circ_table tbody td:nth-child(5),
#circ_table tbody td:nth-child(7) {
    max-height: 2.85em !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    line-height: 1.32 !important;
}

/* 11. Column Allocations for Tables (Institutional Sans-Serif + Tabular Figures) */

/* Top News Table */
#top_news_table th:nth-child(1), #top_news_table td:nth-child(1) { width: 5.5% !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-weight: 700 !important; color: #b45309 !important; }
#top_news_table th:nth-child(2), #top_news_table td:nth-child(2) { width: 8.5% !important; text-align: center !important; font-weight: 600 !important; }
#top_news_table th:nth-child(3), #top_news_table td:nth-child(3) { width: 7% !important; text-align: center !important; font-weight: 700 !important; }
#top_news_table th:nth-child(4), #top_news_table td:nth-child(4) { width: 32% !important; font-weight: 600 !important; color: #0f172a !important; }
#top_news_table th:nth-child(5), #top_news_table td:nth-child(5) { width: 11% !important; color: #475569 !important; font-size: 11px !important; }
#top_news_table th:nth-child(6), #top_news_table td:nth-child(6) { width: 20% !important; color: #334155 !important; font-size: 11px !important; }
#top_news_table th:nth-child(7), #top_news_table td:nth-child(7) { width: 7% !important; font-size: 11px !important; color: #0284c7 !important; font-weight: 600 !important; }
#top_news_table th:nth-child(8), #top_news_table td:nth-child(8) { width: 4% !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-weight: 600 !important; color: #475569 !important; }
#top_news_table th:nth-child(9), #top_news_table td:nth-child(9) { width: 5% !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-size: 11px !important; color: #64748b !important; }

/* Bottom News Table */
#bottom_news_table th:nth-child(1), #bottom_news_table td:nth-child(1) { width: 8% !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-size: 11px !important; color: #64748b !important; }
#bottom_news_table th:nth-child(2), #bottom_news_table td:nth-child(2) { width: 12% !important; color: #0284c7 !important; font-weight: 600 !important; }
#bottom_news_table th:nth-child(3), #bottom_news_table td:nth-child(3) { width: 56% !important; font-weight: 500 !important; color: #0f172a !important; }
#bottom_news_table th:nth-child(4), #bottom_news_table td:nth-child(4) { width: 6% !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-weight: 600 !important; color: #475569 !important; }
#bottom_news_table th:nth-child(5), #bottom_news_table td:nth-child(5) { width: 8% !important; text-align: center !important; }
#bottom_news_table th:nth-child(6), #bottom_news_table td:nth-child(6) { width: 10% !important; text-align: center !important; font-size: 11px !important; color: #2563eb !important; }

/* Calendar Table - 15-Column Layout (With Prominent Date Column & Strict 2-Row Event Clamp) */
#calendar_table,
#calendar_grid_wrap,
#calendar_table .table-wrap,
#calendar_table div[data-testid="dataframe"] {
    width: 100% !important;
    max-width: 100% !important;
    overflow-x: auto !important;
}

#calendar_table table {
    table-layout: fixed !important;
    min-width: 1720px !important;
    width: 1720px !important;
    border-collapse: collapse !important;
}

/* Suppress Svelte 3-dot header action button */
#calendar_table th button,
.gradio-dataframe th button,
div[data-testid="dataframe"] th button,
th button[aria-label*="sort"],
th button[aria-label*="menu"] {
    display: none !important;
    width: 0 !important;
    height: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
    border: none !important;
    pointer-events: none !important;
}

#calendar_table th {
    vertical-align: middle !important;
    padding: 5px 8px !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    white-space: nowrap !important;
    text-overflow: ellipsis !important;
    overflow: hidden !important;
}

#calendar_table th .cell-wrap,
#calendar_table th span {
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}

#calendar_table tbody tr {
    height: 34px !important;
    max-height: 38px !important;
}

#calendar_table tbody td {
    height: 34px !important;
    max-height: 38px !important;
    padding: 3px 6px !important;
    vertical-align: middle !important;
    font-size: 11.5px !important;
    line-height: 1.32 !important;
    overflow: hidden !important;
}

/* Strict 2-row clamp on all cells */
#calendar_table tbody td > *,
#calendar_table tbody td a,
#calendar_table tbody td span,
#calendar_table tbody td div {
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    line-height: 1.32 !important;
    max-height: 2.65em !important;
    word-break: break-word !important;
}

#calendar_table th:nth-child(1), #calendar_table td:nth-child(1) { width: 38px !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; color: #64748b !important; white-space: nowrap !important; }
#calendar_table th:nth-child(2), #calendar_table td:nth-child(2) { width: 95px !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; color: #0f172a !important; font-size: 11px !important; font-weight: 600 !important; white-space: nowrap !important; }
#calendar_table th:nth-child(3), #calendar_table td:nth-child(3) { width: 85px !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; color: #0f172a !important; font-size: 11px !important; white-space: nowrap !important; }
#calendar_table th:nth-child(4), #calendar_table td:nth-child(4) { width: 48px !important; text-align: center !important; font-weight: 600 !important; color: #475569 !important; white-space: nowrap !important; }
#calendar_table th:nth-child(5), #calendar_table td:nth-child(5) { width: 120px !important; text-align: left !important; font-weight: 600 !important; }
#calendar_table th:nth-child(6), #calendar_table td:nth-child(6) { width: 65px !important; text-align: center !important; font-weight: 600 !important; color: #334155 !important; white-space: nowrap !important; }
#calendar_table th:nth-child(7), #calendar_table td:nth-child(7) { width: 75px !important; text-align: center !important; font-weight: 600 !important; color: #0284c7 !important; }
#calendar_table th:nth-child(8), #calendar_table td:nth-child(8) { width: 110px !important; text-align: left !important; color: #475569 !important; }
#calendar_table th:nth-child(9), #calendar_table td:nth-child(9) { width: 320px !important; text-align: left !important; font-weight: 600 !important; color: #0f172a !important; }
#calendar_table th:nth-child(10), #calendar_table td:nth-child(10) { width: 60px !important; text-align: center !important; font-family: var(--font-sans) !important; font-weight: 600 !important; color: #d97706 !important; white-space: nowrap !important; }
#calendar_table th:nth-child(11), #calendar_table td:nth-child(11) { width: 85px !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; color: #475569 !important; font-size: 11px !important; }
#calendar_table th:nth-child(12), #calendar_table td:nth-child(12) { width: 85px !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-weight: 600 !important; color: #059669 !important; font-size: 11px !important; }
#calendar_table th:nth-child(13), #calendar_table td:nth-child(13) { width: 140px !important; text-align: left !important; font-weight: 600 !important; }
#calendar_table th:nth-child(14), #calendar_table td:nth-child(14) { width: 75px !important; text-align: center !important; font-weight: 700 !important; white-space: nowrap !important; }
#calendar_table th:nth-child(15), #calendar_table td:nth-child(15) { width: 275px !important; text-align: left !important; color: #334155 !important; font-size: 11px !important; }

/* Holidays Table */
#holidays_table th:nth-child(1), #holidays_table td:nth-child(1) { width: 8% !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-weight: 600 !important; }
#holidays_table th:nth-child(2), #holidays_table td:nth-child(2) { width: 7% !important; text-align: center !important; }
#holidays_table th:nth-child(3), #holidays_table td:nth-child(3) { width: 23% !important; font-weight: 600 !important; color: #0f172a !important; }
#holidays_table th:nth-child(4), #holidays_table td:nth-child(4) { width: 12% !important; text-align: center !important; }
#holidays_table th:nth-child(5), #holidays_table td:nth-child(5) { width: 12% !important; text-align: center !important; }
#holidays_table th:nth-child(6), #holidays_table td:nth-child(6) { width: 15% !important; text-align: center !important; }
#holidays_table th:nth-child(7), #holidays_table td:nth-child(7) { width: 13% !important; text-align: center !important; }
#holidays_table th:nth-child(8), #holidays_table td:nth-child(8) { width: 10% !important; text-align: center !important; }

/* Regulatory Circulars Table */
#circ_table th:nth-child(1), #circ_table td:nth-child(1) { width: 6% !important; text-align: center !important; font-weight: 700 !important; }
#circ_table th:nth-child(2), #circ_table td:nth-child(2) { width: 9% !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-size: 11px !important; color: #0f172a !important; font-weight: 600 !important; text-align: center !important; }
#circ_table th:nth-child(3), #circ_table td:nth-child(3) { width: 6% !important; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; color: #475569 !important; font-size: 11px !important; }
#circ_table th:nth-child(4), #circ_table td:nth-child(4) { width: 6% !important; text-align: center !important; font-weight: 700 !important; }
#circ_table th:nth-child(5), #circ_table td:nth-child(5) { width: 28% !important; font-weight: 600 !important; color: #0f172a !important; line-height: 1.32 !important; }
#circ_table th:nth-child(6), #circ_table td:nth-child(6) { width: 9% !important; color: #475569 !important; font-size: 11px !important; }
#circ_table th:nth-child(7), #circ_table td:nth-child(7) { width: 27% !important; color: #334155 !important; font-size: 11px !important; line-height: 1.32 !important; }
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
    background: #eff6ff !important;
    color: #2563eb !important;
    border: 1px solid #bfdbfe !important;
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
    margin: -3px -16px 0 -16px !important;
    padding: 2px 14px 2px 14px !important;
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
    display: inline-flex !important;
    align-items: center !important;
    gap: 2px !important;
    background: #f1f5f9 !important;
    padding: 2px !important;
    border-radius: 6px !important;
    border: 1px solid #e2e8f0 !important;
    flex-wrap: nowrap !important;
}

.epm-tab-pill {
    display: inline-flex !important;
    align-items: center !important;
    gap: 5px !important;
    height: 22px !important;
    padding: 0 10px !important;
    font-family: var(--font-sans) !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    border-radius: 4px !important;
    border: none !important;
    background: transparent !important;
    color: #64748b !important;
    cursor: pointer !important;
    transition: all 0.15s cubic-bezier(0.16, 1, 0.3, 1) !important;
    white-space: nowrap !important;
    line-height: 22px !important;
}

.epm-tab-pill .epm-tab-pill-bullet {
    display: inline-block !important;
    width: 5px !important;
    height: 5px !important;
    border-radius: 50% !important;
    background: #94a3b8 !important;
    transition: all 0.15s ease !important;
}

.epm-tab-pill:hover {
    background: rgba(255, 255, 255, 0.6) !important;
    color: #0f172a !important;
}

.epm-tab-pill.active {
    background: #ffffff !important;
    color: #1d4ed8 !important;
    font-weight: 700 !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04) !important;
    border: none !important;
}

.epm-tab-pill.active .epm-tab-pill-bullet {
    background: #2563eb !important;
    box-shadow: 0 0 4px rgba(37, 99, 235, 0.4) !important;
}

.epm-tab-pill.active *,
.epm-tab-pill.active span,
.epm-tab-pill.active .epm-tab-pill-icon {
    color: #1d4ed8 !important;
    font-weight: 700 !important;
}

.epm-tab-pill.active:hover {
    background: #ffffff !important;
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
    background: #2563eb !important;
    color: #ffffff !important;
    border-color: #1d4ed8 !important;
}

.epm-cmd-btn:hover {
    background: #1d4ed8 !important;
    border-color: #1d4ed8 !important;
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

/* 16. Action Deck & Toolbar Cards */
.epm-toolbar-card {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 4px !important;
    padding: 3px 8px !important;
    margin-top: 2px !important;
    margin-bottom: 3px !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02) !important;
}

#cal_action_deck button, #circ_action_toolbar button {
    font-family: var(--font-sans) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    border-radius: 4px !important;
    min-height: 26px !important;
    height: 26px !important;
    padding: 0 8px !important;
    transition: all 0.15s ease !important;
}

#cal_action_deck button.primary, #circ_action_toolbar button.primary {
    background: #2563eb !important;
    color: #ffffff !important;
    border: 1px solid #1d4ed8 !important;
}

#cal_action_deck button.primary:hover, #circ_action_toolbar button.primary:hover {
    background: #1d4ed8 !important;
    border-color: #1d4ed8 !important;
    transform: translateY(-1px) !important;
}

#cal_action_deck button.secondary, #circ_action_toolbar button.secondary {
    background: #f8fafc !important;
    color: #334155 !important;
    border: 1px solid #cbd5e1 !important;
}

#cal_action_deck button.secondary:hover, #circ_action_toolbar button.secondary:hover {
    background: #f1f5f9 !important;
    border-color: #94a3b8 !important;
    color: #0f172a !important;
}

#cal_pdf_file {
    margin-top: 2px !important;
    margin-bottom: 2px !important;
    border: 1px dashed #38bdf8 !important;
    border-radius: 4px !important;
    background: #f0f9ff !important;
    padding: 3px 6px !important;
}

/* 17. Table Header Ribbons & High-Density Integration */
.epm-table-ribbon {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    background: #f8fafc !important;
    border: 1px solid #cbd5e1 !important;
    border-bottom: none !important;
    border-radius: 4px 4px 0 0 !important;
    padding: 2px 8px !important;
    margin-top: 2px !important;
    margin-bottom: 0 !important;
    min-height: 24px !important;
    height: 24px !important;
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
    letter-spacing: 0.02em !important;
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
    font-family: var(--font-sans) !important;
    font-variant-numeric: tabular-nums !important;
    font-feature-settings: "tnum" 1 !important;
    font-size: 9.5px !important;
    font-weight: 600 !important;
    color: #64748b !important;
}

.epm-ribbon-controls {
    display: flex !important;
    align-items: center !important;
    gap: 4px !important;
    flex-wrap: nowrap !important;
}

.epm-ribbon-btn {
    display: inline-flex !important;
    align-items: center !important;
    gap: 3px !important;
    height: 20px !important;
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
    width: 20px !important;
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
    margin-top: 2px !important;
    margin-bottom: 0 !important;
}

#tab1_header_strip .epm-table-ribbon {
    flex: 1 1 auto !important;
    margin-top: 0 !important;
}

#tab1_refresh_btn {
    height: 24px !important;
    min-height: 24px !important;
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
    margin: 2px 0 3px 0 !important;
    padding: 0 !important;
    flex-wrap: nowrap !important;
    overflow-x: auto !important;
    min-height: 26px !important;
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
    display: inline-flex !important;
    flex-direction: row !important;
    align-items: center !important;
    gap: 2px !important;
    margin: 0 !important;
    padding: 2px !important;
    background: #f1f5f9 !important;
    border-radius: 6px !important;
    border: 1px solid #e2e8f0 !important;
    flex-wrap: nowrap !important;
}

#cal_filters_row .wrap label, #circ_filters_row .wrap label {
    display: inline-flex !important;
    align-items: center !important;
    height: 22px !important;
    padding: 0 8px !important;
    border: none !important;
    border-radius: 4px !important;
    background: transparent !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    color: #64748b !important;
    cursor: pointer !important;
    margin: 0 !important;
    transition: all 0.12s ease !important;
    white-space: nowrap !important;
}

#cal_filters_row .wrap label:hover, #circ_filters_row .wrap label:hover {
    background: rgba(255, 255, 255, 0.6) !important;
    color: #0f172a !important;
}

#cal_filters_row .wrap label:has(input:checked), #circ_filters_row .wrap label:has(input:checked) {
    background: #ffffff !important;
    color: #1d4ed8 !important;
    border: none !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08) !important;
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

/* Gapless Ribbon-to-Table Anchor Rules */
div:has(> .epm-table-ribbon),
div:has(> * > .epm-table-ribbon) {
    margin-bottom: 0 !important;
    padding-bottom: 0 !important;
}

div[id*="_table"] {
    margin-top: 0 !important;
    padding-top: 0 !important;
}

div[id*="_table"] .table-wrap,
div[id*="_table"] .gradio-dataframe,
div[id*="_table"] div[data-testid="dataframe"],
div[id*="_table"] .table-container {
    border-top-left-radius: 0 !important;
    border-top-right-radius: 0 !important;
    border-top: none !important;
    margin-top: 0 !important;
    margin-bottom: 6px !important;
}

/* Zero-Height Collapsed Action Messages */
#cal_action_msg,
#circ_action_msg {
    margin: 0 !important;
    padding: 0 !important;
}

#cal_action_msg:not(:has(.prose:not(:empty))),
#cal_action_msg:has(.prose:empty),
#circ_action_msg:not(:has(.prose:not(:empty))),
#circ_action_msg:has(.prose:empty) {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    max-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
}

#cal_action_msg:has(.prose:not(:empty)),
#circ_action_msg:has(.prose:not(:empty)) {
    margin: 3px 0 !important;
    padding: 4px 8px !important;
    font-size: 11.5px !important;
    border-radius: 4px !important;
    background: #f0fdf4 !important;
    border: 1px solid #bbf7d0 !important;
}

/* ═══════════════════════════════════════════════════════════════════
   INSTITUTIONAL PDF DOSSIER MIRROR VIEW (2035 ULTRA-PREMIUM LEDGER)
   ═══════════════════════════════════════════════════════════════════ */

#cal_table_header_strip {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    border-bottom: 2px solid #2563eb !important;
    border-radius: 6px 6px 0 0 !important;
    padding: 3px 8px !important;
    margin-top: 0 !important;
    margin-bottom: 0 !important;
    min-height: 28px !important;
    gap: 8px !important;
    flex-wrap: nowrap !important;
    overflow-x: auto !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
    width: 100% !important;
}

#cal_table_header_strip .epm-tbl-hdr-left,
.epm-tbl-hdr-left {
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
    flex: 0 0 390px !important;
    min-width: 390px !important;
    width: 390px !important;
}

.epm-tbl-hdr-title-group {
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
    white-space: nowrap !important;
}

.epm-tbl-hdr-title {
    font-family: var(--font-sans) !important;
    font-size: 11.5px !important;
    font-weight: 800 !important;
    color: #0f172a !important;
    letter-spacing: 0.4px !important;
}

.epm-tbl-hdr-badge {
    background: #eff6ff !important;
    color: #2563eb !important;
    font-family: var(--font-mono) !important;
    font-size: 9px !important;
    font-weight: 700 !important;
    padding: 1px 5px !important;
    border-radius: 3px !important;
    border: 1px solid #bfdbfe !important;
}

.epm-tbl-hdr-badge-sub {
    font-family: var(--font-mono) !important;
    font-size: 9.5px !important;
    color: #64748b !important;
    font-weight: 500 !important;
}

#cal_table_header_strip .epm-tbl-hdr-actions,
.epm-tbl-hdr-actions {
    display: flex !important;
    align-items: center !important;
    gap: 3px !important;
    justify-content: flex-end !important;
    flex-wrap: nowrap !important;
    flex: 0 0 auto !important;
    margin-left: auto !important;
    width: auto !important;
}

#cal_table_header_strip .epm-tbl-hdr-actions > button,
#cal_table_header_strip .epm-tbl-hdr-actions button,
#cal_table_header_strip button.epm-hdr-action-btn,
.epm-hdr-action-btn {
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: 0 !important;
    max-width: fit-content !important;
    font-family: var(--font-sans) !important;
    font-size: 10px !important;
    font-weight: 600 !important;
    border-radius: 4px !important;
    min-height: 22px !important;
    height: 22px !important;
    padding: 0 5px !important;
    white-space: nowrap !important;
    transition: all 0.12s ease !important;
}

.btn-primary-dark {
    background: #2563eb !important;
    color: #ffffff !important;
    border: 1px solid #1d4ed8 !important;
    box-shadow: 0 1px 2px rgba(37, 99, 235, 0.2) !important;
}

.btn-primary-dark:hover {
    background: #1d4ed8 !important;
    color: #ffffff !important;
    box-shadow: 0 0 6px rgba(37, 99, 235, 0.4) !important;
}

.btn-primary-emerald {
    background: #059669 !important;
    color: #ffffff !important;
    border: 1px solid #047857 !important;
    box-shadow: 0 1px 2px rgba(5, 150, 105, 0.2) !important;
}

.btn-primary-emerald:hover {
    background: #047857 !important;
    color: #ffffff !important;
    box-shadow: 0 0 6px rgba(5, 150, 105, 0.4) !important;
}

.btn-secondary-light {
    background: #ffffff !important;
    color: #334155 !important;
    border: 1px solid #cbd5e1 !important;
}

.btn-secondary-light:hover {
    background: #f8fafc !important;
    color: #0f172a !important;
    border-color: #94a3b8 !important;
}

#calendar_dossier_wrap {
    width: 100% !important;
    margin-top: 0 !important;
    padding-top: 0 !important;
    gap: 0 !important;
}

#calendar_dossier_wrap > * {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

.epm-hidden-action-row {
    display: none !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}

.epm-dossier-container {
    width: 100% !important;
    display: flex;
    flex-direction: column;
    margin-top: 0 !important;
    margin-bottom: 6px !important;
    padding-top: 0 !important;
    border: 1px solid #cbd5e1 !important;
    border-top: none !important;
    border-radius: 0 0 6px 6px !important;
    overflow: hidden !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.03) !important;
}

.epm-dossier-table-wrap {
    width: 100% !important;
    overflow-x: auto !important;
    max-height: 75vh !important;
}

.epm-dossier-table {
    min-width: 1720px !important;
    width: 1720px !important;
    table-layout: fixed !important;
    border-collapse: collapse !important;
    font-family: var(--font-sans) !important;
    font-size: 11.5px !important;
    text-align: left !important;
    background: #ffffff !important;
}

.epm-dossier-table thead th {
    position: sticky !important;
    top: 0 !important;
    z-index: 20 !important;
    background: #f8fafc !important;
    color: #475569 !important;
    font-family: var(--font-sans) !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.02em !important;
    padding: 5px 8px !important;
    border-bottom: 1px solid #cbd5e1 !important;
    border-right: 1px solid #e2e8f0 !important;
    white-space: nowrap !important;
    vertical-align: middle !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
}

.epm-dossier-table thead th:last-child {
    border-right: none !important;
}

/* Sticky Day Group Ribbon */
.epm-day-ribbon-row td {
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    height: auto !important;
    max-height: none !important;
}

.epm-day-ribbon-content {
    position: sticky !important;
    left: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    background: #f1f5f9 !important;
    color: #0f172a !important;
    padding: 3px 10px !important;
    border-top: 1px solid #cbd5e1 !important;
    border-bottom: 1px solid #cbd5e1 !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
}

.epm-ribbon-left {
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
}

.epm-ribbon-bullet {
    display: inline-block !important;
    width: 6px !important;
    height: 6px !important;
    border-radius: 50% !important;
    background: #2563eb !important;
    box-shadow: 0 0 4px rgba(37, 99, 235, 0.4) !important;
}

.epm-ribbon-date {
    font-family: var(--font-sans) !important;
    font-variant-numeric: tabular-nums !important;
    font-feature-settings: "tnum" 1 !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    color: #0f172a !important;
}

.epm-ribbon-day {
    font-family: var(--font-sans) !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    color: #475569 !important;
    text-transform: uppercase !important;
}

.epm-ribbon-tally {
    font-family: var(--font-sans) !important;
    font-variant-numeric: tabular-nums !important;
    font-feature-settings: "tnum" 1 !important;
    font-size: 9.5px !important;
    font-weight: 600 !important;
    background: #e0f2fe !important;
    color: #0284c7 !important;
    border: 1px solid #bae6fd !important;
    padding: 1px 6px !important;
    border-radius: 3px !important;
}

.epm-dossier-row {
    height: 34px !important;
    max-height: 38px !important;
    border-bottom: 1px solid #f1f5f9 !important;
    transition: background 0.1s ease !important;
}

.epm-dossier-row-even {
    background: #ffffff !important;
}

.epm-dossier-row-odd {
    background: #f8fafc !important; /* Subtle zebra striping */
}

.epm-dossier-row:hover {
    background: #f0f7ff !important;
}

.epm-dossier-table td {
    padding: 3px 6px !important;
    vertical-align: middle !important;
    border-right: 1px solid #f1f5f9 !important;
    color: #334155 !important;
    line-height: 1.32 !important;
    height: 34px !important;
    max-height: 38px !important;
    overflow: hidden !important;
    font-family: var(--font-sans) !important;
    font-variant-numeric: tabular-nums !important;
    font-feature-settings: "tnum" 1 !important;
}

.epm-dossier-table td:last-child {
    border-right: none !important;
}

/* Precision Signal Pips */
.epm-signal-pips {
    display: inline-flex !important;
    align-items: center !important;
    gap: 3px !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-family: var(--font-sans) !important;
    font-size: 10px !important;
    font-weight: 700 !important;
    white-space: nowrap !important;
}

.epm-signal-pips .pip {
    display: inline-block !important;
    width: 4px !important;
    height: 10px !important;
    border-radius: 1px !important;
    background: #cbd5e1 !important;
}

.epm-signal-pips.tier-5 {
    background: #fef2f2 !important;
    border: 1px solid #fecaca !important;
    color: #b91c1c !important;
}
.epm-signal-pips.tier-5 .pip.on {
    background: #dc2626 !important;
    box-shadow: 0 0 4px rgba(220, 38, 38, 0.5) !important;
}

.epm-signal-pips.tier-4 {
    background: #fff7ed !important;
    border: 1px solid #fed7aa !important;
    color: #c2410c !important;
}
.epm-signal-pips.tier-4 .pip.on {
    background: #ea580c !important;
}

.epm-signal-pips.tier-3 {
    background: #f0fdf4 !important;
    border: 1px solid #bbf7d0 !important;
    color: #15803d !important;
}
.epm-signal-pips.tier-3 .pip.on {
    background: #16a34a !important;
}

.epm-signal-pips.tier-2, .epm-signal-pips.tier-1 {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    color: #64748b !important;
}
.epm-signal-pips.tier-2 .pip.on, .epm-signal-pips.tier-1 .pip.on {
    background: #64748b !important;
}

.epm-signal-pips .pip-label {
    margin-left: 4px !important;
}

.epm-dossier-table td.col-event,
.epm-dossier-table td.col-event b,
.epm-dossier-table td.col-reason {
    display: -webkit-box !important;
    -webkit-line-clamp: 2 !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    line-height: 1.32 !important;
    max-height: 2.65em !important;
}

.epm-dossier-table .col-idx { width: 36px !important; min-width: 36px; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-size: 10.5px !important; color: #64748b !important; }
.epm-dossier-table .col-date { width: 92px !important; min-width: 92px; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-size: 11px !important; color: #0f172a !important; white-space: nowrap !important; font-weight: 600 !important; }
.epm-dossier-table .col-time { width: 78px !important; min-width: 78px; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-size: 11px !important; color: #0f172a !important; white-space: nowrap !important; }
.epm-dossier-table .col-day { width: 46px !important; min-width: 46px; text-align: center !important; font-weight: 600 !important; color: #475569 !important; white-space: nowrap !important; }
.epm-dossier-table .col-type { width: 115px !important; min-width: 115px; white-space: nowrap !important; }
.epm-dossier-table .col-country { width: 64px !important; min-width: 64px; text-align: center !important; font-weight: 700 !important; color: #1e293b !important; white-space: nowrap !important; }
.epm-dossier-table .col-reg { width: 75px !important; min-width: 75px; text-align: center !important; font-weight: 600 !important; color: #0284c7 !important; }
.epm-dossier-table .col-sec { width: 110px !important; min-width: 110px; color: #475569 !important; }
.epm-dossier-table .col-event { width: 325px !important; min-width: 325px !important; color: #0f172a !important; }
.epm-dossier-table .col-imp { width: 58px !important; min-width: 58px !important; text-align: center !important; white-space: nowrap !important; }
.epm-dossier-table .col-num { width: 88px !important; min-width: 88px; text-align: center !important; font-family: var(--font-sans) !important; font-variant-numeric: tabular-nums !important; font-feature-settings: "tnum" 1 !important; font-size: 11px !important; color: #475569 !important; white-space: nowrap !important; }
.epm-dossier-table .col-fore { color: #059669 !important; font-weight: 600 !important; }
.epm-dossier-table .col-outcome { width: 175px !important; min-width: 175px !important; vertical-align: middle !important; }
.epm-dossier-table .col-sent { width: 80px !important; min-width: 80px; text-align: center !important; white-space: nowrap !important; }
.epm-dossier-table .col-reason { width: 285px !important; min-width: 285px !important; color: #334155 !important; font-size: 11.5px !important; }

/* Unfolded Outcome & Results Badges */
.epm-outcome-pill {
    display: inline-flex !important;
    align-items: center !important;
    gap: 4px !important;
    padding: 2px 7px !important;
    border-radius: 4px !important;
    font-family: var(--font-sans) !important;
    font-variant-numeric: tabular-nums !important;
    font-feature-settings: "tnum" 1 !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    line-height: 1.3 !important;
    max-width: 100% !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
}
.epm-outcome-pill.outcome-released {
    background: #ecfdf5 !important;
    border: 1px solid #a7f3d0 !important;
    color: #065f46 !important;
    font-weight: 700 !important;
}
.epm-outcome-pill.outcome-pending {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    color: #64748b !important;
    font-weight: 500 !important;
}

/* Floating 5 PM Daily Outcomes PDF Pill */
.epm-daily-pdf-floater {
    position: fixed !important;
    bottom: 22px !important;
    right: 26px !important;
    z-index: 999 !important;
    background: #ffffff !important;
    border: 1.5px solid #059669 !important;
    border-radius: 9999px !important;
    box-shadow: 0 4px 16px rgba(5, 150, 105, 0.22), 0 2px 6px rgba(0, 0, 0, 0.08) !important;
    padding: 6px 14px !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 8px !important;
    text-decoration: none !important;
    cursor: pointer !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    backdrop-filter: blur(8px) !important;
}
.epm-daily-pdf-floater:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px rgba(5, 150, 105, 0.32) !important;
    background: #f0fdf4 !important;
    border-color: #047857 !important;
}
.epm-daily-pdf-floater .floater-pulse {
    display: inline-block !important;
    width: 8px !important;
    height: 8px !important;
    border-radius: 50% !important;
    background: #10b981 !important;
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7) !important;
    animation: floater-pulse-anim 2s infinite !important;
}
@keyframes floater-pulse-anim {
    0% {
        transform: scale(0.95);
        box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
    }
    70% {
        transform: scale(1);
        box-shadow: 0 0 0 6px rgba(16, 185, 129, 0);
    }
    100% {
        transform: scale(0.95);
        box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
    }
}
.epm-daily-pdf-floater .floater-label {
    font-family: var(--font-sans) !important;
    font-size: 11.5px !important;
    font-weight: 700 !important;
    color: #065f46 !important;
    letter-spacing: 0.2px !important;
}
.epm-daily-pdf-floater .floater-tag {
    font-family: var(--font-sans) !important;
    font-size: 9.5px !important;
    font-weight: 700 !important;
    background: #ecfdf5 !important;
    color: #047857 !important;
    padding: 1px 6px !important;
    border-radius: 4px !important;
    border: 1px solid #a7f3d0 !important;
}

/* Dossier Badges */
.epm-dossier-badge {
    display: inline-block !important;
    padding: 2px 6px !important;
    border-radius: 3px !important;
    font-size: 10.5px !important;
    font-weight: 700 !important;
    line-height: 1.2 !important;
}
.badge-earnings { color: #15803d !important; background: #f0fdf4 !important; border: 1px solid #bbf7d0 !important; }
.badge-econ { color: #0284c7 !important; background: #f0f9ff !important; border: 1px solid #bae6fd !important; }
.badge-holiday { color: #991b1b !important; background: #fef2f2 !important; border: 1px solid #fecaca !important; }
.badge-special { color: #7c3aed !important; background: #f5f3ff !important; border: 1px solid #ddd6fe !important; }
.badge-corp { color: #334155 !important; background: #f8fafc !important; border: 1px solid #e2e8f0 !important; }
.badge-general { color: #475569 !important; background: #f1f5f9 !important; }

.epm-stars {
    color: #d97706 !important;
    font-family: var(--font-sans) !important;
    font-weight: 700 !important;
    letter-spacing: 0.05em !important;
}

.epm-sent-badge {
    display: inline-block !important;
    padding: 1px 6px !important;
    border-radius: 3px !important;
    font-size: 10px !important;
    font-weight: 700 !important;
}
.sent-bullish { color: #16a34a !important; background: #dcfce7 !important; }
.sent-bearish { color: #dc2626 !important; background: #fee2e2 !important; }
.sent-neutral { color: #64748b !important; background: #f1f5f9 !important; }

.epm-dossier-footer-note {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
    padding: 10px 14px !important;
    text-align: center !important;
    font-size: 11.5px !important;
    color: #64748b !important;
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
    background: #ffffff !important;
    color: #0f172a !important;
    border: 1px solid #cbd5e1 !important;
    padding: 8px 18px !important;
    border-radius: 30px !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1) !important;
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

/* ═══════════════════════════════════════════════════════════════════
   19. 2035 COMMAND PALETTE & ULTRA-PREMIUM NAVIGATION UPGRADES
   ═══════════════════════════════════════════════════════════════════ */

.epm-nav-bolt {
    font-size: 15px !important;
    color: #2563eb !important;
}

.epm-title-highlight {
    color: #2563eb !important;
}

.epm-telem-tg b {
    color: #10b981 !important;
}

.epm-telem-time {
    font-family: var(--font-mono) !important;
    font-size: 10.5px !important;
}

.epm-tab-pill-bullet {
    width: 5px !important;
    height: 5px !important;
    border-radius: 50% !important;
    background: #94a3b8 !important;
    display: inline-block !important;
    transition: background 0.15s ease !important;
}

.epm-tab-pill.active .epm-tab-pill-bullet {
    background: #2563eb !important;
    box-shadow: 0 0 6px #2563eb !important;
}

.epm-cmd-launcher-btn {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    background: #f1f5f9 !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 6px !important;
    padding: 3px 8px !important;
    height: 26px !important;
    cursor: pointer !important;
    transition: all 0.15s ease !important;
}

.epm-cmd-launcher-btn:hover {
    background: #e2e8f0 !important;
    border-color: #94a3b8 !important;
}

.epm-cmd-badge {
    font-family: var(--font-mono) !important;
    font-size: 10px !important;
    font-weight: 700 !important;
    background: #ffffff !important;
    color: #0f172a !important;
    border: 1px solid #cbd5e1 !important;
    padding: 1px 4px !important;
    border-radius: 3px !important;
}

.epm-cmd-label {
    font-family: var(--font-sans) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    color: #475569 !important;
}

/* Command Palette Modal */
.epm-palette-backdrop {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    background: rgba(15, 23, 42, 0.7) !important;
    backdrop-filter: blur(8px) !important;
    -webkit-backdrop-filter: blur(8px) !important;
    z-index: 99999 !important;
    display: none !important;
    align-items: flex-start !important;
    justify-content: center !important;
    padding-top: 12vh !important;
}

.epm-palette-backdrop.is-active {
    display: flex !important;
}

.epm-palette-dialog {
    width: 580px !important;
    max-width: 92vw !important;
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 12px !important;
    box-shadow: 0 20px 40px rgba(0,0,0,0.15), 0 1px 3px rgba(0,0,0,0.08) !important;
    overflow: hidden !important;
    color: #0f172a !important;
    animation: epmPaletteSlide 0.12s ease-out !important;
}

@keyframes epmPaletteSlide {
    from { opacity: 0; transform: translateY(-8px) scale(0.98); }
    to { opacity: 1; transform: translateY(0) scale(1); }
}

.epm-palette-input-wrap {
    display: flex !important;
    align-items: center !important;
    padding: 12px 16px !important;
    border-bottom: 1px solid #e2e8f0 !important;
    gap: 10px !important;
    background: #f8fafc !important;
}

.epm-palette-search-icon {
    font-size: 16px !important;
    color: #2563eb !important;
}

#epm-palette-input {
    flex: 1 !important;
    background: transparent !important;
    border: none !important;
    outline: none !important;
    font-family: var(--font-sans) !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    color: #0f172a !important;
}

#epm-palette-input::placeholder {
    color: #94a3b8 !important;
}

.epm-palette-esc-hint {
    font-family: var(--font-mono) !important;
    font-size: 9.5px !important;
    font-weight: 700 !important;
    background: #f1f5f9 !important;
    color: #475569 !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    border: 1px solid #cbd5e1 !important;
    cursor: pointer !important;
}

.epm-palette-results {
    max-height: 360px !important;
    overflow-y: auto !important;
    padding: 6px !important;
    background: #ffffff !important;
}

.epm-palette-section-title {
    font-family: var(--font-sans) !important;
    font-size: 9.5px !important;
    font-weight: 700 !important;
    color: #64748b !important;
    letter-spacing: 0.04em !important;
    padding: 8px 10px 4px !important;
    text-transform: uppercase !important;
}

.epm-palette-item {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
    padding: 8px 10px !important;
    border-radius: 6px !important;
    cursor: pointer !important;
    transition: background 0.1s ease !important;
}

.epm-palette-item:hover {
    background: #f1f5f9 !important;
}

.epm-item-icon {
    font-size: 15px !important;
}

.epm-item-text {
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
}

.epm-item-main {
    font-size: 12.5px !important;
    font-weight: 600 !important;
    color: #0f172a !important;
}

.epm-item-sub {
    font-size: 11px !important;
    color: #64748b !important;
}

.epm-item-shortcut {
    font-family: var(--font-mono) !important;
    font-size: 9.5px !important;
    background: #eff6ff !important;
    color: #2563eb !important;
    padding: 2px 5px !important;
    border-radius: 3px !important;
    border: 1px solid #bfdbfe !important;
}

/* ═══════════════════════════════════════════════════════════════════════════
   2035 INSTITUTIONAL TABLE TYPOGRAPHY & ZERO MONOSPACE OVERRIDE
   ═══════════════════════════════════════════════════════════════════════════ */
.gradio-container table,
.gradio-container table *,
.gradio-container div[data-testid="dataframe"],
.gradio-container div[data-testid="dataframe"] *,
.gradio-container .table-wrap,
.gradio-container .table-wrap *,
.gradio-container td,
.gradio-container td *,
.gradio-container th,
.gradio-container th *,
.epm-dossier-table,
.epm-dossier-table * {
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "SF Pro Display", "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
}

/* Explicitly reserve tabular figures for numbers & timestamps */
.gradio-container td.col-idx,
.gradio-container td.col-date,
.gradio-container td.col-time,
.gradio-container td.col-num,
.epm-dossier-table .col-idx,
.epm-dossier-table .col-date,
.epm-dossier-table .col-time,
.epm-dossier-table .col-num,
#calendar_table td:nth-child(1),
#calendar_table td:nth-child(2),
#calendar_table td:nth-child(3),
#calendar_table td:nth-child(11),
#calendar_table td:nth-child(12),
#top_news_table td:nth-child(1),
#top_news_table td:nth-child(8),
#top_news_table td:nth-child(9),
#bottom_news_table td:nth-child(1),
#bottom_news_table td:nth-child(4),
#circ_table td:nth-child(2),
#circ_table td:nth-child(3),
#holidays_table td:nth-child(1) {
    font-variant-numeric: tabular-nums !important;
    font-feature-settings: "tnum" 1 !important;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MODULAR WORKSPACE: RE-ORDERABLE & COLLAPSIBLE SECTIONS
   ═══════════════════════════════════════════════════════════════════════════ */
.epm-modular-section {
    display: flex !important;
    flex-direction: column !important;
    margin-bottom: 6px !important;
    padding: 0 !important;
    position: relative !important;
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s ease, opacity 0.15s ease !important;
    border-radius: 4px !important;
}

.epm-modular-section.is-reordering {
    opacity: 0.8 !important;
    transform: scale(0.995) !important;
    background: rgba(37, 99, 235, 0.04) !important;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.3) !important;
}

/* When a section is collapsed, hide everything inside it EXCEPT the ribbon or header strip */
.epm-modular-section.is-collapsed > *:not(.epm-table-ribbon):not(#cal_table_header_strip):not(#tab1_header_strip) {
    display: none !important;
}

.epm-modular-section.is-collapsed .epm-table-ribbon,
.epm-modular-section.is-collapsed #cal_table_header_strip,
.epm-modular-section.is-collapsed #tab1_header_strip {
    border-radius: 4px !important;
    border-bottom: 1px solid #cbd5e1 !important;
    margin-bottom: 2px !important;
}

/* Controls grouping */
.epm-section-ctrl-wrap {
    display: inline-flex !important;
    align-items: center !important;
    gap: 3px !important;
}

.epm-section-reorder-group {
    display: inline-flex !important;
    align-items: center !important;
    gap: 1px !important;
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 3px !important;
    padding: 1px !important;
}

.epm-reorder-btn {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 17px !important;
    height: 17px !important;
    min-height: 17px !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    color: #475569 !important;
    cursor: pointer !important;
    border-radius: 2px !important;
    transition: all 0.12s ease !important;
}

.epm-reorder-btn:hover:not(:disabled) {
    background: #f1f5f9 !important;
    color: #0f172a !important;
}

.epm-reorder-btn:disabled,
.epm-reorder-btn[disabled],
.epm-reorder-btn.is-disabled {
    opacity: 0.3 !important;
    cursor: not-allowed !important;
    pointer-events: none !important;
}

.epm-collapse-btn {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 19px !important;
    height: 19px !important;
    min-height: 19px !important;
    padding: 0 !important;
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 3px !important;
    color: #334155 !important;
    cursor: pointer !important;
    transition: all 0.12s ease !important;
}

.epm-collapse-btn:hover {
    background: #f1f5f9 !important;
    color: #0f172a !important;
    border-color: #94a3b8 !important;
}

.epm-collapse-btn .epm-chevron-icon {
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    display: block !important;
}

.epm-modular-section.is-collapsed .epm-collapse-btn .epm-chevron-icon {
    transform: rotate(-90deg) !important;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MOBILE SIDE DRAWER & INSHORTS PAGE VIEW DRAWER STYLING
   ═══════════════════════════════════════════════════════════════════════════ */

/* Mobile Hamburger Menu Button */
.epm-mobile-menu-trigger {
    display: none !important;
    align-items: center;
    gap: 6px;
    height: 30px;
    padding: 0 10px;
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    cursor: pointer;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
    transition: all 0.15s ease;
    flex-shrink: 0;
}

.epm-mobile-menu-trigger:hover,
.epm-mobile-menu-trigger:active {
    background: #f1f5f9;
    border-color: #94a3b8;
}

.epm-hamburger-line {
    display: block;
    width: 14px;
    height: 2px;
    background-color: #0f172a;
    border-radius: 1px;
    margin: 2px 0;
}

.epm-menu-text {
    font-family: var(--font-sans);
    font-size: 11px;
    font-weight: 700;
    color: #0f172a;
    letter-spacing: 0.04em;
}

/* Mobile Slide-Out Side Navigation Drawer */
.epm-drawer-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.5);
    backdrop-filter: blur(4px);
    z-index: 1040;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.25s ease;
}

.epm-drawer-backdrop.is-open {
    opacity: 1;
    pointer-events: auto;
}

.epm-mobile-drawer {
    position: fixed;
    top: 0;
    right: -320px;
    width: 300px;
    max-width: 86vw;
    height: 100vh;
    background: #ffffff;
    z-index: 1050;
    box-shadow: -8px 0 24px rgba(15, 23, 42, 0.15);
    transition: right 0.28s cubic-bezier(0.16, 1, 0.3, 1);
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}

.epm-mobile-drawer.is-open {
    right: 0;
}

.epm-drawer-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px;
    border-bottom: 1px solid #e2e8f0;
    background: #f8fafc;
}

.epm-drawer-brand {
    display: flex;
    align-items: center;
    gap: 8px;
}

.epm-drawer-title {
    font-family: var(--font-sans);
    font-size: 15px;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.01em;
}

.epm-drawer-badge {
    font-size: 9px;
    font-weight: 700;
    background: #eff6ff;
    color: #2563eb;
    border: 1px solid #bfdbfe;
    padding: 1px 5px;
    border-radius: 4px;
}

.epm-drawer-close-btn {
    width: 28px;
    height: 28px;
    border: 1px solid #cbd5e1;
    background: #ffffff;
    border-radius: 6px;
    color: #64748b;
    font-size: 13px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
}

.epm-drawer-body {
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    flex: 1;
}

.epm-drawer-section-label {
    font-family: var(--font-sans);
    font-size: 10px;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 4px;
}

.epm-drawer-nav-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.epm-drawer-nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    cursor: pointer;
    text-align: left;
    transition: all 0.15s ease;
    width: 100%;
}

.epm-drawer-nav-item:hover,
.epm-drawer-nav-item.active {
    background: #eff6ff;
    border-color: #2563eb;
}

.epm-drawer-item-icon {
    font-size: 18px;
}

.epm-drawer-item-info {
    flex: 1;
    display: flex;
    flex-direction: column;
}

.epm-drawer-item-name {
    font-family: var(--font-sans);
    font-size: 12.5px;
    font-weight: 700;
    color: #0f172a;
}

.epm-drawer-item-desc {
    font-family: var(--font-sans);
    font-size: 10.5px;
    color: #64748b;
}

.epm-drawer-tag {
    font-size: 9.5px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    background: #e2e8f0;
    color: #475569;
}

.epm-drawer-nav-item.active .epm-drawer-tag {
    background: #2563eb;
    color: #ffffff;
}

.epm-drawer-tools {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.epm-drawer-tool-btn {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    font-family: var(--font-sans);
    font-size: 11.5px;
    font-weight: 600;
    color: #0f172a;
    cursor: pointer;
    text-decoration: none;
    transition: all 0.15s ease;
}

.epm-drawer-tool-btn:hover {
    background: #f1f5f9;
    border-color: #94a3b8;
}

.epm-drawer-tool-btn .tool-left {
    display: flex;
    align-items: center;
    gap: 6px;
}

.epm-drawer-tool-btn .tool-kbd {
    font-family: var(--font-mono);
    font-size: 9.5px;
    background: #eff6ff;
    color: #2563eb;
    border: 1px solid #bfdbfe;
    padding: 1px 5px;
    border-radius: 3px;
}

.epm-drawer-tool-btn .tool-badge {
    font-size: 9px;
    font-weight: 700;
    padding: 1px 5px;
    border-radius: 3px;
    background: #eff6ff;
    color: #2563eb;
    border: 1px solid #bfdbfe;
}

.epm-drawer-tool-btn .tool-badge.emerald {
    background: #ecfdf5;
    color: #059669;
    border-color: #a7f3d0;
}

.epm-drawer-footer {
    margin-top: auto;
    padding-top: 12px;
    border-top: 1px solid #f1f5f9;
    font-size: 9.5px;
    color: #94a3b8;
    text-align: center;
}

/* Inshorts Full-Page / Bottom-Sheet Drawer */
.epm-inshorts-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(5px);
    z-index: 1060;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.25s ease;
}

.epm-inshorts-backdrop.is-open {
    opacity: 1;
    pointer-events: auto;
}

.epm-inshorts-drawer {
    position: fixed;
    left: 0;
    right: 0;
    bottom: -110vh;
    max-height: 94vh;
    height: 90vh;
    background: #ffffff;
    border-radius: 18px 18px 0 0;
    box-shadow: 0 -12px 36px rgba(15, 23, 42, 0.25);
    z-index: 1070;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    transition: bottom 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.epm-inshorts-drawer.is-open {
    bottom: 0;
}

.epm-inshorts-handle-bar {
    width: 100%;
    display: flex;
    justify-content: center;
    padding: 8px 0 4px 0;
    cursor: grab;
    flex-shrink: 0;
}

.epm-inshorts-handle {
    width: 36px;
    height: 4px;
    background: #cbd5e1;
    border-radius: 2px;
}

.epm-inshorts-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 16px 10px 16px;
    border-bottom: 1px solid #f1f5f9;
    flex-shrink: 0;
}

.epm-inshorts-meta-strip {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
}

.epm-inshorts-source {
    font-size: 10.5px;
    font-weight: 700;
    color: #0284c7;
    background: #f0f9ff;
    border: 1px solid #bae6fd;
    padding: 2px 7px;
    border-radius: 4px;
}

.epm-inshorts-time {
    font-size: 10px;
    color: #64748b;
    font-family: var(--font-sans);
    font-variant-numeric: tabular-nums;
}

.epm-inshorts-sentiment {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    background: #f1f5f9;
}

.epm-inshorts-sentiment.bullish {
    background: #ecfdf5;
    color: #059669;
}

.epm-inshorts-sentiment.bearish {
    background: #fef2f2;
    color: #dc2626;
}

.epm-inshorts-score {
    font-size: 10px;
    font-weight: 700;
    background: #fef3c7;
    color: #b45309;
    padding: 2px 6px;
    border-radius: 4px;
}

.epm-inshorts-close {
    width: 28px;
    height: 28px;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    background: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 700;
    color: #64748b;
    cursor: pointer;
}

.epm-inshorts-body-scroll {
    padding: 16px 18px;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 14px;
}

.epm-inshorts-hero-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
}

.epm-inshorts-impact-pill {
    font-size: 10.5px;
    font-weight: 800;
    padding: 3px 8px;
    border-radius: 4px;
    background: #fef2f2;
    color: #dc2626;
    border: 1px solid #fecaca;
    letter-spacing: 0.02em;
}

.epm-inshorts-sectors {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
}

.epm-inshorts-tag {
    font-size: 10px;
    font-weight: 600;
    background: #f1f5f9;
    color: #334155;
    padding: 2px 6px;
    border-radius: 4px;
}

.epm-inshorts-title {
    font-family: var(--font-sans);
    font-size: 18px;
    font-weight: 800;
    line-height: 1.35;
    color: #0f172a;
    letter-spacing: -0.02em;
    margin: 0;
}

.epm-inshorts-section {
    display: flex;
    flex-direction: column;
    gap: 6px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px 14px;
}

.epm-inshorts-section-heading {
    font-size: 10.5px;
    font-weight: 800;
    color: #475569;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.epm-inshorts-reasoning-text {
    font-family: var(--font-sans);
    font-size: 13.5px;
    line-height: 1.55;
    color: #1e293b;
}

.epm-inshorts-metrics-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
}

.epm-metric-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 8px 4px;
    text-align: center;
}

.epm-metric-card.highlight {
    background: #f0fdf4;
    border-color: #86efac;
}

.epm-metric-card .m-label {
    font-size: 9px;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}

.epm-metric-card .m-val {
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 700;
    color: #0f172a;
    margin-top: 2px;
}

.epm-metric-card.highlight .m-val {
    color: #166534;
}

.epm-inshorts-footer-note {
    font-size: 10px;
    color: #94a3b8;
    text-align: center;
    padding: 8px 0;
}

/* Inshorts Fixed Bottom Bar */
.epm-inshorts-bottom-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    background: #ffffff;
    border-top: 1px solid #e2e8f0;
    box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.03);
    flex-shrink: 0;
}

.epm-inshorts-primary-action {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 8px 12px;
    background: linear-gradient(135deg, #1d4ed8, #2563eb);
    color: #ffffff;
    border-radius: 8px;
    text-decoration: none;
    cursor: pointer;
    box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);
    transition: all 0.15s ease;
}

.epm-inshorts-primary-action .action-txt {
    font-size: 12.5px;
    font-weight: 700;
}

.epm-inshorts-primary-action .action-sub {
    font-size: 9.5px;
    opacity: 0.85;
}

.epm-inshorts-dismiss-btn {
    height: 38px;
    padding: 0 12px;
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 700;
    color: #334155;
    cursor: pointer;
}

/* Body lock when drawer is open */
body.epm-drawer-locked {
    overflow: hidden !important;
}

/* ═══════════════════════════════════════════════════════════════════════════
   MOBILE & TABLET RESPONSIVE SYSTEM (Dual-Axis Touch Scroller & Layout Adapt)
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Tablet & Small Laptops (<= 1024px) ── */
@media (max-width: 1024px) {
    .gradio-container, 
    .gradio-container > .main, 
    .gradio-container > .wrap,
    div[class*="gradio-container"] {
        padding: 2px 8px 10px 8px !important;
    }

    .epm-nav-row-1 {
        gap: 6px !important;
    }

    #epm-telemetry-ticker {
        gap: 8px !important;
    }

    .epm-nav-row-2 {
        gap: 6px !important;
    }

    .epm-quick-tab-btn {
        padding: 0 8px !important;
        font-size: 11px !important;
    }

    #cal_table_header_strip .epm-tbl-hdr-left {
        min-width: 280px !important;
        width: 280px !important;
        flex: 0 0 280px !important;
    }

    #cal_table_header_strip button.epm-hdr-action-btn {
        padding: 0 6px !important;
        font-size: 10px !important;
    }
}

/* ── Mobile Devices & Phablets (<= 767px) ── */
@media (max-width: 767px) {
    /* 1. Global Touch Viewport Reset */
    html, body {
        width: 100% !important;
        max-width: 100vw !important;
        overflow-x: hidden !important;
    }

    .gradio-container, 
    .gradio-container > .main, 
    .gradio-container > .wrap,
    div[class*="gradio-container"] {
        padding: 2px 4px 8px 4px !important;
        width: 100% !important;
        max-width: 100vw !important;
    }

    /* 2. Top Navigation Bar on Mobile (Header + MENU Button only, clean news dashboard) */
    .epm-top-navbar {
        height: auto !important;
        min-height: auto !important;
        padding: 6px 10px !important;
        margin-bottom: 6px !important;
        gap: 0 !important;
    }

    .epm-nav-row-1 {
        flex-direction: row !important;
        align-items: center !important;
        justify-content: space-between !important;
        height: 36px !important;
        gap: 8px !important;
        padding: 0 !important;
    }

    .epm-nav-brand-cluster {
        width: auto !important;
        flex: 1 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        gap: 6px !important;
        overflow: hidden !important;
    }

    .epm-nav-brand-cluster .epm-nav-telemetry {
        display: none !important;
    }

    .epm-mobile-menu-trigger {
        display: flex !important;
        flex-shrink: 0 !important;
    }

    #epm-telemetry-ticker {
        display: none !important;
    }

    .epm-nav-row-2 {
        display: none !important;
    }

    /* Interactive Touch Card & Row Feedback (Mobile List to Inshorts Drawer) */
    #top_news_table tbody tr,
    #bottom_news_table tbody tr,
    #circ_table tbody tr,
    #calendar_table tbody tr,
    .epm-dossier-row,
    .epm-card.epm-news-card {
        cursor: pointer !important;
        -webkit-tap-highlight-color: rgba(37, 99, 235, 0.15) !important;
        transition: background-color 0.15s ease, transform 0.15s ease !important;
    }

    #top_news_table tbody tr:active,
    #bottom_news_table tbody tr:active,
    #circ_table tbody tr:active,
    #calendar_table tbody tr:active,
    .epm-dossier-row:active {
        background-color: #eff6ff !important;
    }

    /* 3. Dual-Axis Table Scrollers with Sticky Headers & Sticky Index Column */
    .table-wrap,
    .gradio-dataframe,
    div[data-testid="dataframe"],
    .epm-dossier-table-wrap {
        width: 100% !important;
        max-width: 100% !important;
        overflow-x: auto !important;
        overflow-y: auto !important;
        max-height: 68vh !important;
        -webkit-overflow-scrolling: touch !important;
        overscroll-behavior: contain !important;
        border-radius: 0 0 4px 4px !important;
    }

    /* Enforce Min-Widths so table columns never crush on small screens */
    #top_news_table table {
        min-width: 890px !important;
        width: 890px !important;
        table-layout: fixed !important;
    }

    #bottom_news_table table {
        min-width: 780px !important;
        width: 780px !important;
        table-layout: fixed !important;
    }

    #circ_table table {
        min-width: 950px !important;
        width: 950px !important;
        table-layout: fixed !important;
    }

    #holidays_table table {
        min-width: 740px !important;
        width: 740px !important;
        table-layout: fixed !important;
    }

    #calendar_table table,
    .epm-dossier-table {
        min-width: 1720px !important;
        width: 1720px !important;
        table-layout: fixed !important;
    }

    /* Vertical Sticky Headers */
    .gradio-container thead th,
    .epm-dossier-table thead th {
        position: sticky !important;
        top: 0 !important;
        z-index: 10 !important;
        background-color: #f8fafc !important;
        box-shadow: 0 2px 4px rgba(15, 23, 42, 0.05) !important;
    }

    /* Horizontal Sticky Column 1 */
    #top_news_table th:nth-child(1),
    #top_news_table td:nth-child(1),
    #bottom_news_table th:nth-child(1),
    #bottom_news_table td:nth-child(1),
    #circ_table th:nth-child(1),
    #circ_table td:nth-child(1),
    #holidays_table th:nth-child(1),
    #holidays_table td:nth-child(1),
    .epm-dossier-table th.col-idx,
    .epm-dossier-table td.col-idx {
        position: sticky !important;
        left: 0 !important;
        z-index: 5 !important;
        background-color: #ffffff !important;
        box-shadow: 2px 0 4px rgba(15, 23, 42, 0.04) !important;
    }

    .gradio-container thead th:nth-child(1),
    .epm-dossier-table thead th.col-idx {
        z-index: 12 !important;
        background-color: #f8fafc !important;
    }

    /* 4. Table Header Ribbons on Mobile */
    .epm-table-ribbon {
        padding: 3px 6px !important;
        gap: 4px !important;
    }

    .epm-ribbon-title {
        font-size: 10.5px !important;
    }

    .epm-ribbon-badge {
        display: none !important;
    }

    .epm-ribbon-btn {
        height: 20px !important;
        padding: 0 5px !important;
        font-size: 9.5px !important;
    }

    /* 5. Mobile Filter Rows */
    #cal_filters_row, #circ_filters_row {
        flex-direction: column !important;
        align-items: stretch !important;
        gap: 4px !important;
        margin: 2px 0 4px 0 !important;
        overflow-x: visible !important;
    }

    #cal_filters_row .gradio-radio, #circ_filters_row .gradio-radio {
        width: 100% !important;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        scrollbar-width: none !important;
    }

    #cal_filters_row .wrap, #circ_filters_row .wrap {
        display: inline-flex !important;
        flex-direction: row !important;
        width: max-content !important;
        padding: 2px !important;
        gap: 2px !important;
    }

    #cal_filters_row .wrap label, #circ_filters_row .wrap label {
        min-height: 26px !important;
        height: 26px !important;
        line-height: 26px !important;
        padding: 0 8px !important;
        font-size: 10.5px !important;
        flex-shrink: 0 !important;
    }

    #circ_filters_row .gradio-textbox {
        width: 100% !important;
        margin-top: 2px !important;
    }

    #circ_filters_row .gradio-textbox input {
        height: 28px !important;
        font-size: 12px !important;
        width: 100% !important;
    }

    /* 6. Action Toolbars on Mobile */
    #cal_table_header_strip {
        flex-direction: column !important;
        align-items: stretch !important;
        height: auto !important;
        padding: 4px 6px !important;
        gap: 4px !important;
    }

    #cal_table_header_strip .epm-tbl-hdr-left {
        width: 100% !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
        justify-content: space-between !important;
    }

    .epm-tbl-hdr-title {
        font-size: 10.5px !important;
    }

    .epm-tbl-hdr-badge-sub {
        display: none !important;
    }

    #cal_table_header_strip .epm-tbl-hdr-actions {
        width: 100% !important;
        justify-content: flex-start !important;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        scrollbar-width: none !important;
        gap: 3px !important;
        padding-bottom: 2px !important;
    }

    #cal_table_header_strip button.epm-hdr-action-btn {
        min-height: 24px !important;
        height: 24px !important;
        padding: 0 6px !important;
        font-size: 9.5px !important;
        flex-shrink: 0 !important;
    }

    #circ_action_toolbar {
        flex-direction: column !important;
        gap: 4px !important;
        padding: 4px !important;
    }

    #circ_action_toolbar button {
        width: 100% !important;
        min-height: 30px !important;
        height: auto !important;
        padding: 4px 8px !important;
        font-size: 10.5px !important;
        white-space: normal !important;
        text-align: center !important;
        line-height: 1.3 !important;
    }

    #tab1_header_strip {
        flex-direction: column !important;
        align-items: stretch !important;
        gap: 4px !important;
    }

    #tab1_refresh_btn {
        width: 100% !important;
        min-height: 28px !important;
        justify-content: center !important;
    }

    /* 7. Floating 5 PM Download Button */
    .epm-daily-pdf-floater {
        bottom: 8px !important;
        right: 8px !important;
        padding: 4px 8px !important;
    }
    .epm-daily-pdf-floater .floater-label {
        font-size: 10px !important;
    }
    .epm-daily-pdf-floater .floater-tag {
        display: none !important;
    }
}

/* ── Ultra-Compact Screen Refinements (<= 430px: iPhone 13/14/15/16 Pro, Galaxy S24) ── */
@media (max-width: 430px) {
    .epm-nav-title {
        font-size: 12px !important;
    }

    .epm-telem-pill {
        font-size: 8.5px !important;
        padding: 0 4px !important;
        height: 16px !important;
    }

    .epm-cmd-launcher-btn {
        padding: 0 4px !important;
    }

    .epm-cmd-badge {
        font-size: 9px !important;
        padding: 0 2px !important;
    }

    .epm-daily-pdf-floater {
        bottom: 8px !important;
        right: 8px !important;
        padding: 4px 8px !important;
    }
    .epm-daily-pdf-floater .floater-label {
        font-size: 10px !important;
    }
    .epm-daily-pdf-floater .floater-tag {
        display: none !important;
    }
}
"""


TOP_NAVBAR_HTML = """
<div id="epm-top-navbar" class="epm-top-navbar">
    <!-- Row 1: Brand Identity, Live Telemetry & Macro Ticker Strip -->
    <div class="epm-nav-row-1">
        <!-- Brand Cluster & Compact System Telemetry -->
        <div class="epm-nav-brand-cluster">
            <span class="epm-nav-bolt">⚡</span>
            <span class="epm-nav-title">EPM<span class="epm-title-highlight">PRO</span></span>
            <span class="epm-nav-version">v3.5 WIRE</span>
            <div class="epm-nav-status-badge">
                <span class="epm-live-dot"></span>
                <span>ONLINE</span>
            </div>
            <!-- High-Density Inline System Telemetry -->
            <div class="epm-nav-telemetry">
                <span class="epm-telem-pill" title="Cached Live News Catalysts">NEWS <b id="epm-hdr-news">88</b></span>
                <span class="epm-telem-pill" title="5-Market Scheduled Events">CAL <b id="epm-hdr-cal">872</b></span>
                <span class="epm-telem-pill" title="Official Regulatory Circulars">CIRC <b id="epm-hdr-circ">23</b></span>
                <span class="epm-telem-pill epm-telem-tg" title="Telegram Forwarder Status">TG <b id="epm-hdr-tg">ACTIVE</b></span>
                <span class="epm-telem-pill epm-telem-time" title="Current Time (IST)"><b id="epm-hdr-ist">12:50:00 IST</b></span>
            </div>
        </div>

        <!-- Mobile Menu Trigger Button (Visible strictly on mobile screens) -->
        <button type="button" id="epm-mobile-menu-btn" class="epm-mobile-menu-trigger" onclick="window.epmToggleMobileMenu()" title="Open Navigation Menu">
            <span class="epm-hamburger-line"></span>
            <span class="epm-hamburger-line"></span>
            <span class="epm-hamburger-line"></span>
            <span class="epm-menu-text">MENU</span>
        </button>

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

    <!-- Row 2: Unified Navigation Tabs (Left) + Command Bar & Controls (Right) -->
    <div class="epm-nav-row-2">
        <!-- 5 Page Navigation Tabs -->
        <div class="epm-quick-tabs-container">
            <button type="button" class="epm-tab-pill active" onclick="window.epmSwitchTab(0, this)">
                <span class="epm-tab-pill-bullet"></span>
                <span>Live Wire</span>
            </button>
            <button type="button" class="epm-tab-pill" onclick="window.epmSwitchTab(1, this)">
                <span class="epm-tab-pill-bullet"></span>
                <span>Market Calendar</span>
            </button>
            <button type="button" class="epm-tab-pill" onclick="window.epmSwitchTab(2, this)">
                <span class="epm-tab-pill-bullet"></span>
                <span>Regulatory Circulars</span>
            </button>
            <button type="button" class="epm-tab-pill" onclick="window.epmSwitchTab(3, this)">
                <span class="epm-tab-pill-bullet"></span>
                <span>Settings Hub</span>
            </button>
            <button type="button" class="epm-tab-pill" onclick="window.epmSwitchTab(4, this)">
                <span class="epm-tab-pill-bullet"></span>
                <span>User Guide</span>
            </button>
        </div>

        <!-- Quick Utilities & Actions -->
        <div class="epm-nav-controls">
            <!-- Bloomberg Command Launcher -->
            <button type="button" class="epm-cmd-launcher-btn" onclick="window.epmOpenPalette()" title="Press Cmd+K or / to open Command Palette">
                <span class="epm-cmd-badge">⌘K /</span>
                <span class="epm-cmd-label">Quick Jump & Tickers</span>
            </button>

            <!-- Watchlist Highlighter Input -->
            <div class="epm-nav-search-wrap" title="Highlight table rows matching keywords/tickers">
                <span class="epm-nav-search-icon">⌕</span>
                <input id="epm-watchlist-input" type="text" placeholder="Highlight Ticker..." oninput="window.epmApplyWatchlist(this.value)">
                <span id="epm-watchlist-count" class="epm-watchlist-badge" style="display:none;">0</span>
                <button type="button" class="epm-watchlist-clear-btn" onclick="window.epmClearWatchlist()" title="Clear highlighter">✕</button>
            </div>

            <!-- Audio Alert Toggle -->
            <button type="button" id="epm-audio-toggle-btn" class="epm-top-btn epm-btn-active" onclick="window.epmToggleAudio()" title="Toggle Web Audio Flash Chime (880Hz -> 1320Hz)">
                <span class="epm-btn-icon">⚡</span>
                <span id="epm-audio-status-lbl">Audio ON</span>
            </button>
        </div>
    </div>
</div>

<!-- 2035 Institutional Command Palette Modal -->
<div id="epm-command-palette-modal" class="epm-palette-backdrop" style="display:none;" onclick="if(event.target===this)window.epmClosePalette()">
    <div class="epm-palette-dialog">
        <div class="epm-palette-input-wrap">
            <span class="epm-palette-search-icon">⚡</span>
            <input id="epm-palette-input" type="text" placeholder="Search ticker (RELIANCE, NIFTY, CRUDE), jump to page, or run action..." oninput="window.epmFilterPalette(this.value)" autocomplete="off">
            <kbd class="epm-palette-esc-hint" onclick="window.epmClosePalette()">ESC</kbd>
        </div>
        <div id="epm-palette-results" class="epm-palette-results">
            <div class="epm-palette-section-title">NAVIGATION WORKSPACES</div>
            <div class="epm-palette-item" onclick="window.epmSwitchTab(0);window.epmClosePalette()">
                <span class="epm-item-icon">📰</span>
                <div class="epm-item-text"><span class="epm-item-main">Live Wire News Stream</span><span class="epm-item-sub">Real-time multi-market intelligence feed</span></div>
                <span class="epm-item-shortcut">Tab 1</span>
            </div>
            <div class="epm-palette-item" onclick="window.epmSwitchTab(1);window.epmClosePalette()">
                <span class="epm-item-icon">📅</span>
                <div class="epm-item-text"><span class="epm-item-main">Unified Catalyst Ledger & Calendar</span><span class="epm-item-sub">15-column date-enriched institutional dossier</span></div>
                <span class="epm-item-shortcut">Tab 2</span>
            </div>
            <div class="epm-palette-item" onclick="window.epmSwitchTab(2);window.epmClosePalette()">
                <span class="epm-item-icon">📜</span>
                <div class="epm-item-text"><span class="epm-item-main">Official Regulatory Directives</span><span class="epm-item-sub">SEBI, RBI, NSE, BSE, MCX official circulars</span></div>
                <span class="epm-item-shortcut">Tab 3</span>
            </div>
            <div class="epm-palette-section-title">DOSSIER DISPATCH & EXPORTS</div>
            <div class="epm-palette-item" onclick="window.epmPaletteAction('download_weekly');window.epmClosePalette()">
                <span class="epm-item-icon">📥</span>
                <div class="epm-item-text"><span class="epm-item-main">Download Weekly Snapshot PDF</span><span class="epm-item-sub">Next Sunday to Saturday (A4 Landscape Print-Ready)</span></div>
                <span class="epm-item-shortcut">PDF</span>
            </div>
            <div class="epm-palette-item" onclick="window.epmPaletteAction('download_monthly');window.epmClosePalette()">
                <span class="epm-item-icon">📥</span>
                <div class="epm-item-text"><span class="epm-item-main">Download Monthly Outlook PDF</span><span class="epm-item-sub">Upcoming Full Month Outlook (A4 Landscape)</span></div>
                <span class="epm-item-shortcut">PDF</span>
            </div>
            <div class="epm-palette-item" onclick="window.epmPaletteAction('push_weekly');window.epmClosePalette()">
                <span class="epm-item-icon">✈️</span>
                <div class="epm-item-text"><span class="epm-item-main">Push Weekly Dossier to Telegram</span><span class="epm-item-sub">Manual execution of Friday 6 AM scheduled dispatch</span></div>
                <span class="epm-item-shortcut">Dispatch</span>
            </div>
            <div class="epm-palette-item" onclick="window.epmPaletteAction('push_monthly');window.epmClosePalette()">
                <span class="epm-item-icon">✈️</span>
                <div class="epm-item-text"><span class="epm-item-main">Push Monthly Dossier to Telegram</span><span class="epm-item-sub">Manual execution of 25th 6 AM scheduled dispatch</span></div>
                <span class="epm-item-shortcut">Dispatch</span>
            </div>
            <div class="epm-palette-item" onclick="window.epmToggleAudio();window.epmClosePalette()">
                <span class="epm-item-icon">🔔</span>
                <div class="epm-item-text"><span class="epm-item-main">Toggle Web Audio Alert Synthesizer</span><span class="epm-item-sub">Dual-tone harmonic 880Hz to 1320Hz chime</span></div>
                <span class="epm-item-shortcut">Audio</span>
            </div>
        </div>
    </div>
</div>

<!-- Mobile Slide-Out Side Navigation Drawer -->
<div id="epm-mobile-drawer-backdrop" class="epm-drawer-backdrop" onclick="window.epmCloseMobileMenu()"></div>
<div id="epm-mobile-drawer" class="epm-mobile-drawer">
    <div class="epm-drawer-header">
        <div class="epm-drawer-brand">
            <span class="epm-nav-bolt">⚡</span>
            <span class="epm-drawer-title">EPM<span class="epm-title-highlight">PRO</span></span>
            <span class="epm-drawer-badge">v3.5 WIRE</span>
        </div>
        <button type="button" class="epm-drawer-close-btn" onclick="window.epmCloseMobileMenu()">✕</button>
    </div>

    <div class="epm-drawer-body">
        <div class="epm-drawer-section-label">SELECT WORKSPACE VIEW</div>
        <div class="epm-drawer-nav-list">
            <button type="button" class="epm-drawer-nav-item active" data-tab="0" onclick="window.epmSwitchTab(0);window.epmCloseMobileMenu()">
                <span class="epm-drawer-item-icon">📰</span>
                <div class="epm-drawer-item-info">
                    <span class="epm-drawer-item-name">Live Financial Wire</span>
                    <span class="epm-drawer-item-desc">Breaking news catalysts & AI sentiment</span>
                </div>
                <span class="epm-drawer-tag">Feed</span>
            </button>
            <button type="button" class="epm-drawer-nav-item" data-tab="1" onclick="window.epmSwitchTab(1);window.epmCloseMobileMenu()">
                <span class="epm-drawer-item-icon">📅</span>
                <div class="epm-drawer-item-info">
                    <span class="epm-drawer-item-name">Market Calendar & Outcomes</span>
                    <span class="epm-drawer-item-desc">15-column catalyst ledger & 5 PM results</span>
                </div>
                <span class="epm-drawer-tag">Ledger</span>
            </button>
            <button type="button" class="epm-drawer-nav-item" data-tab="2" onclick="window.epmSwitchTab(2);window.epmCloseMobileMenu()">
                <span class="epm-drawer-item-icon">📜</span>
                <div class="epm-drawer-item-info">
                    <span class="epm-drawer-item-name">Regulatory Circulars & PDFs</span>
                    <span class="epm-drawer-item-desc">NSE, BSE, MCX, RBI, FINMIN, FOMC</span>
                </div>
                <span class="epm-drawer-tag">Directives</span>
            </button>
            <button type="button" class="epm-drawer-nav-item" data-tab="3" onclick="window.epmSwitchTab(3);window.epmCloseMobileMenu()">
                <span class="epm-drawer-item-icon">⚙️</span>
                <div class="epm-drawer-item-info">
                    <span class="epm-drawer-item-name">Portal Settings & Integrations</span>
                    <span class="epm-drawer-item-desc">Telegram channels & automated alerts</span>
                </div>
                <span class="epm-drawer-tag">Admin</span>
            </button>
            <button type="button" class="epm-drawer-nav-item" data-tab="4" onclick="window.epmSwitchTab(4);window.epmCloseMobileMenu()">
                <span class="epm-drawer-item-icon">❓</span>
                <div class="epm-drawer-item-info">
                    <span class="epm-drawer-item-name">User Guide & Shortcuts</span>
                    <span class="epm-drawer-item-desc">Terminal manual & quick commands</span>
                </div>
                <span class="epm-drawer-tag">Docs</span>
            </button>
        </div>

        <div class="epm-drawer-section-label">INSTITUTIONAL TOOLS & EXPORTS</div>
        <div class="epm-drawer-tools">
            <button type="button" class="epm-drawer-tool-btn" onclick="window.epmCloseMobileMenu();window.epmOpenPalette()">
                <span class="tool-left"><span class="tool-icon">⚡</span> ⌘K Quick Jump & Search</span>
                <span class="tool-kbd">⌘K /</span>
            </button>
            <button type="button" class="epm-drawer-tool-btn" onclick="window.epmToggleAudio()">
                <span class="tool-left"><span class="tool-icon">🔔</span> Audio Flash Chime</span>
                <span id="epm-drawer-audio-state" class="tool-badge">ON</span>
            </button>
            <a href="/api/calendar/pdf/daily-outcomes" download class="epm-drawer-tool-btn" onclick="window.epmCloseMobileMenu()">
                <span class="tool-left"><span class="tool-icon">📥</span> 5 PM Daily Outcomes PDF</span>
                <span class="tool-badge emerald">A4 PDF</span>
            </a>
            <a href="/api/calendar/pdf/weekly" download class="epm-drawer-tool-btn" onclick="window.epmCloseMobileMenu()">
                <span class="tool-left"><span class="tool-icon">📥</span> Weekly Snapshot PDF</span>
                <span class="tool-badge">A4 PDF</span>
            </a>
            <a href="/api/calendar/pdf/monthly" download class="epm-drawer-tool-btn" onclick="window.epmCloseMobileMenu()">
                <span class="tool-left"><span class="tool-icon">📥</span> Monthly Outlook PDF</span>
                <span class="tool-badge">A4 PDF</span>
            </a>
        </div>

        <div class="epm-drawer-footer">
            <span>Global News Feed Room is Powered by EPMC Pvt. Ltd.</span>
        </div>
    </div>
</div>

<!-- Inshorts-Style Mobile Page View Drawer (Bottom Sheet) -->
<div id="epm-inshorts-backdrop" class="epm-inshorts-backdrop" onclick="window.epmCloseInshortsDrawer()"></div>
<div id="epm-inshorts-drawer" class="epm-inshorts-drawer">
    <div class="epm-inshorts-handle-bar">
        <div class="epm-inshorts-handle"></div>
    </div>
    
    <div class="epm-inshorts-header">
        <div class="epm-inshorts-meta-strip">
            <span id="epm-inshorts-source" class="epm-inshorts-source">REUTERS</span>
            <span id="epm-inshorts-time" class="epm-inshorts-time">⏱️ 14:30 IST</span>
            <span id="epm-inshorts-sentiment" class="epm-inshorts-sentiment">🟢 BULLISH</span>
            <span id="epm-inshorts-score" class="epm-inshorts-score">AI 9/10</span>
        </div>
        <button type="button" class="epm-inshorts-close" onclick="window.epmCloseInshortsDrawer()" title="Close Page View">✕</button>
    </div>

    <div class="epm-inshorts-body-scroll">
        <div id="epm-inshorts-hero-banner" class="epm-inshorts-hero-banner">
            <div id="epm-inshorts-impact-pill" class="epm-inshorts-impact-pill">🚨 HIGH IMPACT MARKET CATALYST</div>
            <div id="epm-inshorts-sectors" class="epm-inshorts-sectors"></div>
        </div>

        <h2 id="epm-inshorts-title" class="epm-inshorts-title">Market Headline Loading...</h2>

        <div class="epm-inshorts-section">
            <div class="epm-inshorts-section-heading">💡 AI EXECUTIVE BREAKDOWN & REASONING</div>
            <div id="epm-inshorts-reasoning" class="epm-inshorts-reasoning-text"></div>
        </div>

        <!-- Optional fields for Calendar Events (Previous, Forecast, Results) -->
        <div id="epm-inshorts-cal-metrics" class="epm-inshorts-metrics-grid" style="display:none;">
            <div class="epm-metric-card">
                <span class="m-label">PREVIOUS</span>
                <span id="epm-metric-prev" class="m-val">—</span>
            </div>
            <div class="epm-metric-card">
                <span class="m-label">FORECAST</span>
                <span id="epm-metric-fore" class="m-val">—</span>
            </div>
            <div class="epm-metric-card highlight">
                <span class="m-label">ACTUAL RESULTS</span>
                <span id="epm-metric-act" class="m-val">⏳ Pending</span>
            </div>
        </div>

        <!-- Optional fields for Regulatory Circulars -->
        <div id="epm-inshorts-circ-metrics" class="epm-inshorts-metrics-grid" style="display:none;">
            <div class="epm-metric-card">
                <span class="m-label">AUTHORITY</span>
                <span id="epm-metric-reg" class="m-val">NSE</span>
            </div>
            <div class="epm-metric-card">
                <span class="m-label">CIRCULAR NO.</span>
                <span id="epm-metric-circno" class="m-val">—</span>
            </div>
            <div class="epm-metric-card highlight">
                <span class="m-label">CLASSIFICATION</span>
                <span id="epm-metric-cat" class="m-val">Directive</span>
            </div>
        </div>

        <div class="epm-inshorts-footer-note">
            <span>Verified Institutional Feed · Powered by EPMC Pvt. Ltd.</span>
        </div>
    </div>

    <!-- Fixed Bottom Inshorts Action Bar ("Tap to know more") -->
    <div class="epm-inshorts-bottom-bar">
        <a id="epm-inshorts-action-link" href="#" target="_blank" rel="noopener noreferrer" class="epm-inshorts-primary-action">
            <span class="action-txt">Tap to Read Full Story / Official Document ↗</span>
            <span class="action-sub">Opens original authenticated source directly</span>
        </a>
        <button type="button" class="epm-inshorts-dismiss-btn" onclick="window.epmCloseInshortsDrawer()">✕ Close</button>
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
        const drawerAudioState = document.getElementById("epm-drawer-audio-state");
        if (drawerAudioState) {
            drawerAudioState.textContent = audioMuted ? "OFF" : "ON";
            if (audioMuted) {
                drawerAudioState.classList.remove("emerald");
            } else {
                drawerAudioState.classList.add("emerald");
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
        const drawerItems = document.querySelectorAll('.epm-drawer-nav-item');
        drawerItems.forEach((d, idx) => {
            if (idx === tabIdx) d.classList.add('active');
            else d.classList.remove('active');
        });
        const badge = document.getElementById("epm-active-tab-indicator");
        if (badge && TAB_NAMES[tabIdx]) {
            badge.textContent = TAB_NAMES[tabIdx];
        }
    }

    // 3. Single Standard High-Density View (Controls Eradicated)
    window.epmSetDensity = function() {};
    window.epmCycleGlobalDensity = function() {};
    window.epmSetGlobalDensity = function() {};

    // 4. Modular Section Reordering & Drag/Shift Engine
    window.epmMoveSection = function(sectionId, direction) {
        let el = document.getElementById(sectionId) || document.querySelector(`[data-section="${sectionId}"]`);
        if (!el) {
            el = document.getElementById('sec_' + sectionId);
        }
        if (!el) return;

        // If target is inside an epm-modular-section, find parent container
        const sec = el.classList.contains('epm-modular-section') ? el : el.closest('.epm-modular-section');
        if (!sec || !sec.parentElement) return;

        const parent = sec.parentElement;
        const sections = Array.from(parent.children).filter(c => c.classList.contains('epm-modular-section'));
        const currentIndex = sections.indexOf(sec);

        if (direction === 'up' && currentIndex > 0) {
            const targetSec = sections[currentIndex - 1];
            parent.insertBefore(sec, targetSec);
            sec.classList.add('is-reordering');
            setTimeout(() => sec.classList.remove('is-reordering'), 350);
            window.epmSaveSectionOrder(parent);
            window.epmUpdateReorderButtons(parent);
        } else if (direction === 'down' && currentIndex < sections.length - 1) {
            const targetSec = sections[currentIndex + 1];
            parent.insertBefore(targetSec, sec);
            sec.classList.add('is-reordering');
            setTimeout(() => sec.classList.remove('is-reordering'), 350);
            window.epmSaveSectionOrder(parent);
            window.epmUpdateReorderButtons(parent);
        }
    };

    window.epmUpdateReorderButtons = function(container) {
        if (!container) return;
        const sections = Array.from(container.children).filter(c => c.classList.contains('epm-modular-section'));
        sections.forEach((sec, idx) => {
            const upBtn = sec.querySelector('.epm-move-up');
            const downBtn = sec.querySelector('.epm-move-down');
            if (upBtn) {
                upBtn.disabled = (idx === 0);
                upBtn.classList.toggle('is-disabled', idx === 0);
            }
            if (downBtn) {
                downBtn.disabled = (idx === sections.length - 1);
                downBtn.classList.toggle('is-disabled', idx === sections.length - 1);
            }
        });
    };

    window.epmSaveSectionOrder = function(container) {
        if (!container) return;
        const tabEl = container.closest('.tabitem, [role="tabpanel"], div[id*="tab"]');
        const tabId = tabEl ? (tabEl.id || tabEl.getAttribute('aria-label') || 'default_tab') : 'default_tab';
        const sections = Array.from(container.children).filter(c => c.classList.contains('epm-modular-section'));
        const orderIds = sections.map(s => s.id).filter(id => Boolean(id));
        if (orderIds.length > 0) {
            localStorage.setItem('epm_order_' + tabId, JSON.stringify(orderIds));
        }
    };

    window.epmRestoreSectionOrder = function() {
        const containers = document.querySelectorAll('.tabitem, [role="tabpanel"], .gradio-tabitem, div[id*="tab"]');
        containers.forEach(tabEl => {
            const tabId = tabEl.id || tabEl.getAttribute('aria-label') || 'default_tab';
            const saved = localStorage.getItem('epm_order_' + tabId);
            if (!saved) return;
            try {
                const orderIds = JSON.parse(saved);
                const sectionMap = {};
                const sections = Array.from(tabEl.querySelectorAll('.epm-modular-section'));
                if (sections.length <= 1) return;
                
                const parent = sections[0].parentElement;
                sections.forEach(s => { if (s.id) sectionMap[s.id] = s; });

                orderIds.forEach(id => {
                    if (sectionMap[id] && sectionMap[id].parentElement === parent) {
                        parent.appendChild(sectionMap[id]);
                    }
                });
                window.epmUpdateReorderButtons(parent);
            } catch(e) {}
        });
    };

    // 5. Section Collapse / Expand Controller with Rotating Chevron & Persistence
    window.epmToggleCollapse = function(targetId, btn) {
        let el = document.getElementById(targetId) || document.querySelector(`[data-section="${targetId}"]`);
        if (!el) {
            el = document.getElementById('sec_' + targetId);
        }
        if (!el) return;

        // If target is or is inside an epm-modular-section, collapse entire section body
        const sec = el.classList.contains('epm-modular-section') ? el : el.closest('.epm-modular-section');
        if (sec) {
            const isCollapsed = sec.classList.toggle('is-collapsed');
            const secId = sec.id || targetId;
            localStorage.setItem('epm_collapsed_' + secId, isCollapsed ? 'true' : 'false');

            const chevron = sec.querySelector('.epm-collapse-btn .epm-chevron-icon') || (btn ? btn.querySelector('.epm-chevron-icon') : null);
            if (chevron) {
                chevron.style.transform = isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)';
            }
            const b = btn || sec.querySelector('.epm-collapse-btn');
            if (b) {
                b.title = isCollapsed ? 'Expand section' : 'Collapse section';
                b.classList.toggle('is-active', isCollapsed);
            }
            return;
        }

        // Standalone table fallback
        const isCollapsed = el.classList.toggle('epm-table-collapsed');
        localStorage.setItem('epm_collapsed_' + targetId, isCollapsed ? 'true' : 'false');
        if (btn) {
            const chevron = btn.querySelector('.epm-chevron-icon');
            if (chevron) chevron.style.transform = isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)';
            btn.title = isCollapsed ? 'Expand table' : 'Collapse table';
            btn.classList.toggle('is-active', isCollapsed);
        }
    };

    // 6. Restore Collapse States
    window.epmRestoreCollapseStates = function() {
        const sections = document.querySelectorAll('.epm-modular-section, div[id*="_table"]');
        sections.forEach(sec => {
            const secId = sec.id;
            if (!secId) return;
            const isCollapsed = localStorage.getItem('epm_collapsed_' + secId) === 'true';
            if (isCollapsed) {
                if (sec.classList.contains('epm-modular-section')) {
                    sec.classList.add('is-collapsed');
                    const chevron = sec.querySelector('.epm-collapse-btn .epm-chevron-icon');
                    if (chevron) chevron.style.transform = 'rotate(-90deg)';
                    const b = sec.querySelector('.epm-collapse-btn');
                    if (b) {
                        b.title = 'Expand section';
                        b.classList.add('is-active');
                    }
                } else {
                    sec.classList.add('epm-table-collapsed');
                    const ribbon = document.querySelector(`.epm-table-ribbon[data-target="${secId}"]`);
                    if (ribbon) {
                        const btn = ribbon.querySelector('.epm-collapse-btn');
                        if (btn) {
                            const chevron = btn.querySelector('.epm-chevron-icon');
                            if (chevron) chevron.style.transform = 'rotate(-90deg)';
                            btn.title = 'Expand table';
                            btn.classList.add('is-active');
                        }
                    }
                }
            }
        });
    };

    // 7. Reset Layout to Default
    window.epmResetLayout = function() {
        Object.keys(localStorage).forEach(k => {
            if (k.startsWith('epm_order_') || k.startsWith('epm_collapsed_')) {
                localStorage.removeItem(k);
            }
        });
        location.reload();
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

    // 8. Action Drawers (Legacy compatibility stubs)
    window.epmToggleCalDrawer = function() {};
    window.epmToggleCircDrawer = function() {};

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
        updateISTClock();
        syncTelemetryFromStatusBox();
        initTerminalStream();

        const savedQuery = localStorage.getItem("epm_watchlist") || "";
        if (savedQuery) {
            window.epmApplyWatchlist(savedQuery);
        }

        window.epmRestoreSectionOrder();
        window.epmRestoreCollapseStates();

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
                setTimeout(() => {
                    window.epmRestoreSectionOrder();
                    window.epmRestoreCollapseStates();
                }, 80);
            });
        });

        wireTableInshortsClicks();
        setupInshortsSwipeDismiss();
    }

    // 11. Fast Server-Sent Events (SSE) Delta Stream
    function initTerminalStream() {
        if (!window.EventSource) return;
        try {
            const es = new EventSource('/api/stream/terminal');
            es.addEventListener('telemetry', function(e) {
                try {
                    const data = JSON.parse(e.data);
                    if (data.news_count !== undefined) {
                        const el = document.getElementById("epm-hdr-news");
                        if (el) el.textContent = data.news_count;
                    }
                    if (data.cal_count !== undefined) {
                        const el = document.getElementById("epm-hdr-cal");
                        if (el) el.textContent = data.cal_count;
                    }
                    if (data.circ_count !== undefined) {
                        const el = document.getElementById("epm-hdr-circ");
                        if (el) el.textContent = data.circ_count;
                    }
                    if (data.timestamp) {
                        const el = document.getElementById("epm-hdr-ist");
                        if (el) el.textContent = data.timestamp;
                    }
                } catch(err) {}
            });
        } catch(err) {}
    }

    // 12. Bloomberg-Style Command Palette (Cmd+K / '/')
    window.epmOpenPalette = function() {
        const modal = document.getElementById('epm-command-palette-modal');
        const input = document.getElementById('epm-palette-input');
        if (modal) {
            modal.classList.add('is-active');
            if (input) {
                input.value = '';
                setTimeout(() => input.focus(), 50);
                window.epmFilterPalette('');
            }
        }
    };

    window.epmClosePalette = function() {
        const modal = document.getElementById('epm-command-palette-modal');
        if (modal) modal.classList.remove('is-active');
    };

    window.epmFilterPalette = function(query) {
        const items = document.querySelectorAll('#epm-palette-results .epm-palette-item');
        const q = (query || '').toLowerCase().trim();
        items.forEach(el => {
            const txt = el.innerText.toLowerCase();
            el.style.display = (!q || txt.includes(q)) ? 'flex' : 'none';
        });
    };

    window.epmPaletteAction = function(action) {
        if (action === 'download_weekly') {
            const btns = document.querySelectorAll('button');
            for (let b of btns) {
                if (b.innerText.includes('Weekly PDF')) { b.click(); break; }
            }
        } else if (action === 'download_monthly') {
            const btns = document.querySelectorAll('button');
            for (let b of btns) {
                if (b.innerText.includes('Monthly PDF')) { b.click(); break; }
            }
        } else if (action === 'push_weekly') {
            const btns = document.querySelectorAll('button');
            for (let b of btns) {
                if (b.innerText.includes('Push Weekly')) { b.click(); break; }
            }
        } else if (action === 'push_monthly') {
            const btns = document.querySelectorAll('button');
            for (let b of btns) {
                if (b.innerText.includes('Push Monthly')) { b.click(); break; }
            }
        }
    };

    // 13. Mobile Navigation Menu Side Drawer Controller
    window.epmToggleMobileMenu = function() {
        const drawer = document.getElementById('epm-mobile-drawer');
        if (!drawer) return;
        if (drawer.classList.contains('is-open')) {
            window.epmCloseMobileMenu();
        } else {
            window.epmOpenMobileMenu();
        }
    };

    window.epmOpenMobileMenu = function() {
        const drawer = document.getElementById('epm-mobile-drawer');
        const backdrop = document.getElementById('epm-mobile-drawer-backdrop');
        if (drawer) drawer.classList.add('is-open');
        if (backdrop) backdrop.classList.add('is-open');
        document.body.classList.add('epm-drawer-locked');
    };

    window.epmCloseMobileMenu = function() {
        const drawer = document.getElementById('epm-mobile-drawer');
        const backdrop = document.getElementById('epm-mobile-drawer-backdrop');
        if (drawer) drawer.classList.remove('is-open');
        if (backdrop) backdrop.classList.remove('is-open');
        document.body.classList.remove('epm-drawer-locked');
    };

    // 14. Inshorts-Style Mobile Page View Drawer (Bottom Sheet) Controller
    window.epmOpenInshortsDrawer = function(data) {
        if (!data) return;
        const drawer = document.getElementById('epm-inshorts-drawer');
        const backdrop = document.getElementById('epm-inshorts-backdrop');
        if (!drawer || !backdrop) return;

        // Source
        const srcEl = document.getElementById('epm-inshorts-source');
        if (srcEl) srcEl.textContent = (data.source || 'WIRE').toUpperCase();

        // Time
        const timeEl = document.getElementById('epm-inshorts-time');
        if (timeEl) timeEl.textContent = data.time ? `⏱️ ${data.time}` : '⏱️ Live';

        // Sentiment
        const sentEl = document.getElementById('epm-inshorts-sentiment');
        if (sentEl) {
            const sent = (data.sentiment || 'NEUTRAL').toUpperCase();
            sentEl.textContent = sent;
            sentEl.className = 'epm-inshorts-sentiment';
            if (sent.includes('BULL')) sentEl.classList.add('bullish');
            else if (sent.includes('BEAR')) sentEl.classList.add('bearish');
        }

        // Score
        const scoreEl = document.getElementById('epm-inshorts-score');
        if (scoreEl) scoreEl.textContent = data.score || 'AI 8/10';

        // Impact Banner
        const impactEl = document.getElementById('epm-inshorts-impact-pill');
        if (impactEl) impactEl.textContent = (data.impact || 'MARKET CATALYST').toUpperCase();

        // Sectors
        const secWrap = document.getElementById('epm-inshorts-sectors');
        if (secWrap) {
            secWrap.innerHTML = '';
            if (data.sectors && data.sectors.length > 0) {
                data.sectors.forEach(s => {
                    const tag = document.createElement('span');
                    tag.className = 'epm-inshorts-tag';
                    tag.textContent = s;
                    secWrap.appendChild(tag);
                });
            }
        }

        // Title
        const titleEl = document.getElementById('epm-inshorts-title');
        if (titleEl) titleEl.textContent = data.title || 'Market Catalyst';

        // AI Reasoning
        const reasEl = document.getElementById('epm-inshorts-reasoning');
        if (reasEl) {
            reasEl.textContent = data.reasoning || 'Detailed AI quantitative reasoning analyzed across multi-market financial news feeds.';
        }

        // Calendar Metrics Grid
        const calGrid = document.getElementById('epm-inshorts-cal-metrics');
        if (calGrid) {
            if (data.type === 'calendar') {
                calGrid.style.display = 'grid';
                const p = document.getElementById('epm-metric-prev');
                const f = document.getElementById('epm-metric-fore');
                const a = document.getElementById('epm-metric-act');
                if (p) p.textContent = data.prev || '—';
                if (f) f.textContent = data.fore || '—';
                if (a) a.textContent = data.act || '⏳ Pending';
            } else {
                calGrid.style.display = 'none';
            }
        }

        // Circular Metrics Grid
        const circGrid = document.getElementById('epm-inshorts-circ-metrics');
        if (circGrid) {
            if (data.type === 'circular') {
                circGrid.style.display = 'grid';
                const r = document.getElementById('epm-metric-reg');
                const c = document.getElementById('epm-metric-circno');
                const k = document.getElementById('epm-metric-cat');
                if (r) r.textContent = data.reg || data.source || 'NSE';
                if (c) c.textContent = data.circNo || '—';
                if (k) k.textContent = data.cat || 'Directive';
            } else {
                circGrid.style.display = 'none';
            }
        }

        // Action Link
        const linkEl = document.getElementById('epm-inshorts-action-link');
        if (linkEl) {
            const link = data.link && data.link !== '#' ? data.link : '';
            if (link) {
                linkEl.href = link;
                linkEl.style.display = 'flex';
                const txtEl = linkEl.querySelector('.action-txt');
                if (txtEl) {
                    txtEl.textContent = data.type === 'circular' ? 'Tap to View / Download Official PDF ↗' : 'Tap to Read Full Story / Document ↗';
                }
            } else {
                linkEl.style.display = 'none';
            }
        }

        // Open drawer
        drawer.classList.add('is-open');
        backdrop.classList.add('is-open');
        document.body.classList.add('epm-drawer-locked');
    };

    window.epmCloseInshortsDrawer = function() {
        const drawer = document.getElementById('epm-inshorts-drawer');
        const backdrop = document.getElementById('epm-inshorts-backdrop');
        if (drawer) {
            drawer.classList.remove('is-open');
            drawer.style.transform = '';
        }
        if (backdrop) backdrop.classList.remove('is-open');
        document.body.classList.remove('epm-drawer-locked');
    };

    function wireTableInshortsClicks() {
        document.addEventListener('click', function(e) {
            const isMobile = window.innerWidth <= 820;

            const row = e.target.closest('#top_news_table tbody tr, #bottom_news_table tbody tr, #circ_table tbody tr, #calendar_table tbody tr');
            const card = e.target.closest('.epm-card.epm-news-card, .epm-circ-card, .epm-dossier-row');

            if (!row && !card) return;

            let data = null;

            if (row) {
                const tableWrap = row.closest('[id]');
                const tid = tableWrap ? tableWrap.id : '';
                const cells = Array.from(row.querySelectorAll('td'));
                if (!cells || cells.length === 0) return;

                if (tid === 'top_news_table' && cells.length >= 7) {
                    const score = cells[0]?.innerText.trim() || 'AI 8/10';
                    const sent = cells[1]?.innerText.trim() || 'NEUTRAL';
                    const impact = cells[2]?.innerText.trim() || 'HIGH';
                    const titleAnchor = cells[3]?.querySelector('a');
                    const title = titleAnchor ? titleAnchor.innerText.trim() : (cells[3]?.innerText.trim() || '');
                    const link = titleAnchor ? titleAnchor.getAttribute('href') : '#';
                    const sectors = cells[4]?.innerText.trim() || '';
                    const reasoning = cells[5]?.innerText.trim() || '';
                    const source = cells[6]?.innerText.trim() || 'Live Wire';
                    const time = cells[8]?.innerText.trim() || '';

                    data = {
                        type: 'news',
                        title: title,
                        link: link,
                        source: source,
                        time: time,
                        score: score.startsWith('AI') ? score : `AI ${score}`,
                        sentiment: sent,
                        impact: impact,
                        sectors: sectors ? sectors.split(/[,/]+/).map(s => s.trim()).filter(Boolean) : [],
                        reasoning: reasoning
                    };
                } else if (tid === 'bottom_news_table' && cells.length >= 5) {
                    const time = cells[0]?.innerText.trim() || '';
                    const source = cells[1]?.innerText.trim() || 'Market Feed';
                    const titleAnchor = cells[2]?.querySelector('a');
                    const title = titleAnchor ? titleAnchor.innerText.trim() : (cells[2]?.innerText.trim() || '');
                    const link = titleAnchor ? titleAnchor.getAttribute('href') : (cells[5]?.querySelector('a')?.getAttribute('href') || '#');
                    const sent = cells[4]?.innerText.trim() || 'NEUTRAL';

                    data = {
                        type: 'news',
                        title: title,
                        link: link,
                        source: source,
                        time: time,
                        score: 'Standard',
                        sentiment: sent,
                        impact: 'GENERAL WIRE',
                        sectors: [],
                        reasoning: 'Automated news feed wire monitored across global institutional market desks.'
                    };
                } else if (tid === 'circ_table' && cells.length >= 7) {
                    const reg = cells[0]?.innerText.trim() || 'Official';
                    const circNo = cells[1]?.innerText.trim() || '—';
                    const date = cells[2]?.innerText.trim() || '';
                    const impact = cells[3]?.innerText.trim() || 'Directive';
                    const titleAnchor = cells[4]?.querySelector('a');
                    const title = titleAnchor ? titleAnchor.innerText.trim() : (cells[4]?.innerText.trim() || '');
                    const link = titleAnchor ? titleAnchor.getAttribute('href') : (cells[7]?.querySelector('a')?.getAttribute('href') || '#');
                    const cat = cells[5]?.innerText.trim() || 'Regulatory Filing';
                    const summary = cells[6]?.innerText.trim() || '';

                    data = {
                        type: 'circular',
                        title: title,
                        link: link,
                        source: reg,
                        time: date,
                        score: impact,
                        sentiment: '⚪ OFFICIAL',
                        impact: `${reg} REGULATORY DIRECTIVE`,
                        sectors: [cat],
                        reasoning: summary,
                        circNo: circNo,
                        reg: reg,
                        cat: cat
                    };
                } else if (tid === 'calendar_table' && cells.length >= 14) {
                    const date = cells[1]?.innerText.trim() || '';
                    const time = cells[2]?.innerText.trim() || '';
                    const evType = cells[4]?.innerText.trim() || 'Event';
                    const reg = cells[6]?.innerText.trim() || '';
                    const sector = cells[7]?.innerText.trim() || '';
                    const rawName = cells[8]?.innerText.trim() || '';
                    const prev = cells[10]?.innerText.trim() || '—';
                    const fore = cells[11]?.innerText.trim() || '—';
                    const act = cells[12]?.innerText.trim() || '⏳ Pending';
                    const sent = cells[13]?.innerText.trim() || 'NEUTRAL';
                    const reasoning = cells[14]?.innerText.trim() || '';

                    data = {
                        type: 'calendar',
                        title: rawName,
                        link: '#',
                        source: reg || evType,
                        time: `${date} ${time}`.trim(),
                        score: evType,
                        sentiment: sent,
                        impact: `${reg || 'MARKET'} CATALYST`,
                        sectors: sector ? [sector] : [],
                        reasoning: reasoning,
                        prev: prev,
                        fore: fore,
                        act: act
                    };
                }
            } else if (card) {
                if (card.classList.contains('epm-news-card')) {
                    const titleAnchor = card.querySelector('.epm-news-title');
                    const title = titleAnchor ? titleAnchor.innerText.replace('↗', '').trim() : '';
                    const link = titleAnchor ? titleAnchor.getAttribute('href') : '#';
                    const source = card.querySelector('.epm-source-chip')?.innerText.trim() || 'Wire';
                    const time = card.querySelector('.epm-time-chip')?.innerText.trim() || '';
                    const score = card.querySelector('.epm-score-pill')?.innerText.trim() || 'AI 8/10';
                    const sent = card.querySelector('.epm-badge[class*="sent-"]')?.innerText.trim() || 'NEUTRAL';
                    const impact = card.querySelector('.epm-badge[class*="impact-"]')?.innerText.trim() || 'CATALYST';
                    const reasoning = card.querySelector('.epm-news-reasoning')?.innerText.trim() || '';
                    const sectorEls = card.querySelectorAll('.epm-sector-tag');
                    const sectors = Array.from(sectorEls).map(el => el.innerText.trim()).filter(Boolean);

                    data = {
                        type: 'news',
                        title: title,
                        link: link,
                        source: source,
                        time: time,
                        score: score,
                        sentiment: sent,
                        impact: impact,
                        sectors: sectors,
                        reasoning: reasoning
                    };
                } else if (card.classList.contains('epm-circ-card')) {
                    const titleAnchor = card.querySelector('a');
                    const title = titleAnchor ? titleAnchor.innerText.trim() : (card.querySelector('h3, h4')?.innerText.trim() || '');
                    const link = titleAnchor ? titleAnchor.getAttribute('href') : '#';
                    const source = card.querySelector('.regulator, .badge')?.innerText.trim() || 'Regulator';
                    const summary = card.innerText;

                    data = {
                        type: 'circular',
                        title: title,
                        link: link,
                        source: source,
                        time: 'Official Notice',
                        score: 'Directive',
                        sentiment: '⚪ OFFICIAL',
                        impact: 'REGULATORY DIRECTIVE',
                        sectors: [],
                        reasoning: summary
                    };
                }
            }

            if (data && data.title && data.title !== '-' && !data.title.includes('Awaiting incoming')) {
                if (isMobile || e.target.tagName !== 'A') {
                    e.preventDefault();
                    window.epmOpenInshortsDrawer(data);
                }
            }
        }, true);
    }

    function setupInshortsSwipeDismiss() {
        const drawer = document.getElementById('epm-inshorts-drawer');
        if (!drawer) return;

        let startY = 0;
        let currentY = 0;

        drawer.addEventListener('touchstart', function(e) {
            startY = e.touches[0].clientY;
            currentY = startY;
        }, { passive: true });

        drawer.addEventListener('touchmove', function(e) {
            currentY = e.touches[0].clientY;
            const diff = currentY - startY;
            if (diff > 0 && drawer.scrollTop <= 0) {
                drawer.style.transform = `translateY(${Math.min(diff, 180)}px)`;
            }
        }, { passive: true });

        drawer.addEventListener('touchend', function() {
            const diff = currentY - startY;
            drawer.style.transform = '';
            if (diff > 80) {
                window.epmCloseInshortsDrawer();
            }
        });
    }

    window.addEventListener('keydown', function(e) {
        const tag = (document.activeElement && document.activeElement.tagName) ? document.activeElement.tagName.toLowerCase() : '';
        const isInput = tag === 'input' || tag === 'textarea';
        
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            window.epmOpenPalette();
        } else if (e.key === '/' && !isInput) {
            e.preventDefault();
            window.epmOpenPalette();
        } else if (e.key === 'Escape') {
            window.epmClosePalette();
        }
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", epmInitTerminal);
    } else {
        epmInitTerminal();
    }
    window.addEventListener("load", epmInitTerminal);
    
    setInterval(() => {
        const savedQuery = localStorage.getItem("epm_watchlist");
        if (savedQuery) window.epmApplyWatchlist(savedQuery);
        
        const dossierWrap = document.getElementById("calendar_dossier_wrap");
        if (dossierWrap && dossierWrap.style.display !== "block") {
            dossierWrap.style.setProperty('display', 'block', 'important');
        }

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
    status_box = gr.Markdown(value=init_status_str, elem_id="epm-status-box", visible=False)

    with gr.Tabs(overflow_behavior="wrap"):
        # ═══════════════════════════════════════════════════════════
        # TAB 1: Live Financial Wire & Breaking Catalysts
        # ═══════════════════════════════════════════════════════════
        with gr.TabItem("📰 Live Financial Wire & Breaking Catalysts"):
            with gr.Column(elem_id="sec_breaking_wire", elem_classes=["epm-modular-section"]):
                with gr.Row(elem_id="tab1_header_strip"):
                    gr.HTML(render_table_ribbon("top_news_table", "Institutional Breaking Wire", subtitle="AI Scored ≥ 7", count_badge="Primary Catalysts", section_id="sec_breaking_wire"))
                    refresh_btn = gr.Button("🔄 Force Refresh Feeds", variant="primary", elem_id="tab1_refresh_btn", scale=0)

                top_table = gr.Dataframe(
                    headers=["Score", "Sentiment", "Impact", "Headline", "Sectors/Tickers", "AI Reasoning", "Source", "Relevance", "Time"],
                    datatype=["str", "str", "str", "markdown", "str", "str", "str", "str", "str"],
                    value=init_top_rows,
                    interactive=False,
                    wrap=True,
                    elem_id="top_news_table"
                )

            with gr.Column(elem_id="sec_secondary_wire", elem_classes=["epm-modular-section"]):
                gr.HTML(render_table_ribbon("bottom_news_table", "Broad Market Secondary Stream", subtitle="All Feeds", count_badge="Raw Wire", section_id="sec_secondary_wire"))
                bottom_table = gr.Dataframe(
                    headers=["Time", "Source", "Headline", "Relevance", "Sentiment", "URL"],
                    datatype=["str", "str", "markdown", "str", "str", "markdown"],
                    value=init_bottom_rows,
                    interactive=False,
                    wrap=True,
                    elem_id="bottom_news_table"
                )

            with gr.Column(elem_id="sec_visual_news", elem_classes=["epm-modular-section"]):
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
            cal_info_bar = gr.Markdown(value=init_cal_summary, elem_id="cal_info_bar", visible=False)

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

            with gr.Column(elem_id="sec_catalyst_ledger", elem_classes=["epm-modular-section"]):
                with gr.Column(elem_id="calendar_dossier_wrap"):
                    with gr.Row(elem_id="cal_table_header_strip", elem_classes=["epm-table-header-integrated"]):
                        with gr.Row(elem_classes=["epm-tbl-hdr-left"]):
                            gr.HTML("""
                            <div class="epm-tbl-hdr-title-group">
                                <span class="epm-ribbon-bullet">●</span>
                                <span class="epm-tbl-hdr-title">MULTI-MARKET CATALYST DOSSIER</span>
                                <span class="epm-tbl-hdr-badge">15-COLUMN SCHEMA</span>
                                <span class="epm-tbl-hdr-badge-sub">Auto: Daily 5 PM · Fri 6 AM · 25th 6 AM</span>
                            </div>
                            """)
                        with gr.Row(elem_classes=["epm-tbl-hdr-actions"]):
                            btn_download_daily_outcomes = gr.Button("📥 5 PM PDF", variant="primary", elem_classes=["epm-hdr-action-btn", "btn-primary-emerald"])
                            btn_push_daily_outcomes = gr.Button("✈️ Push 5 PM", variant="secondary", elem_classes=["epm-hdr-action-btn", "btn-secondary-light"])
                            btn_download_weekly = gr.Button("📥 Weekly PDF", variant="primary", elem_classes=["epm-hdr-action-btn", "btn-primary-dark"])
                            btn_download_monthly = gr.Button("📥 Monthly PDF", variant="primary", elem_classes=["epm-hdr-action-btn", "btn-primary-dark"])
                            btn_push_weekly_pdf = gr.Button("✈️ Weekly", variant="secondary", elem_classes=["epm-hdr-action-btn", "btn-secondary-light"])
                            btn_push_monthly_pdf = gr.Button("✈️ Monthly", variant="secondary", elem_classes=["epm-hdr-action-btn", "btn-secondary-light"])
                            btn_sync_gcal = gr.Button("📅 GCal", variant="secondary", elem_classes=["epm-hdr-action-btn", "btn-secondary-light"])
                            btn_ics_export = gr.Button("📲 .ICS", variant="secondary", elem_classes=["epm-hdr-action-btn", "btn-secondary-light"])
                            btn_push_holiday = gr.Button("🏖️ Holidays", variant="secondary", elem_classes=["epm-hdr-action-btn", "btn-secondary-light"])
                            gr.HTML(render_section_controls("sec_catalyst_ledger"))

                    calendar_visual_feed = gr.HTML(value=init_cal_html, elem_id="calendar_visual_feed")

            with gr.Row(elem_classes=["epm-hidden-action-row"]):
                cal_action_msg = gr.Markdown(elem_id="cal_action_msg")
                cal_pdf_file = gr.File(label="📄 PDF Dossier Ready for Download (Click to Open / Save)", visible=False, elem_id="cal_pdf_file")

            calendar_table = gr.Dataframe(
                headers=[
                    "#",
                    "Date",
                    "Time (IST)",
                    "Day",
                    "Event Type",
                    "Country",
                    "Reg.",
                    "Sector",
                    "Event",
                    "Impact",
                    "Previous",
                    "Forecast",
                    "Results",
                    "Sentiment",
                    "AI Reasoning"
                ],
                datatype=["str"] * 15,
                value=init_cal_rows,
                interactive=False,
                wrap=True,
                visible=False,
                elem_id="calendar_table"
            )

            with gr.Column(elem_id="sec_holidays_ledger", elem_classes=["epm-modular-section"]):
                gr.HTML(render_table_ribbon("holidays_table", "2026 Authoritative Trading Holidays", subtitle="NSE · BSE · MCX · NYSE · CRYPTO", count_badge="All Sessions", section_id="sec_holidays_ledger"))
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
            btn_sync_gcal.click(trigger_sync_google_cal, outputs=[cal_action_msg])
            btn_push_holiday.click(push_holiday_check_alert, outputs=[cal_action_msg])
            btn_download_daily_outcomes.click(handle_download_daily_outcomes_pdf, outputs=[cal_action_msg, cal_pdf_file])
            btn_push_daily_outcomes.click(handle_dispatch_daily_outcomes_pdf_telegram, outputs=[cal_action_msg, cal_pdf_file])
            btn_download_weekly.click(handle_download_weekly_pdf, outputs=[cal_action_msg, cal_pdf_file])
            btn_download_monthly.click(handle_download_monthly_pdf, outputs=[cal_action_msg, cal_pdf_file])
            btn_push_weekly_pdf.click(handle_dispatch_weekly_pdf_telegram, outputs=[cal_action_msg, cal_pdf_file])
            btn_push_monthly_pdf.click(handle_dispatch_monthly_pdf_telegram, outputs=[cal_action_msg, cal_pdf_file])
            btn_ics_export.click(handle_download_ics_file, outputs=[cal_action_msg, cal_pdf_file])
            save_ev_btn.click(
                handle_manual_event_save,
                inputs=[in_ev_id, in_ev_mkt, in_ev_date, in_ev_time, in_ev_sym, in_ev_name, in_ev_imp, in_ev_prev, in_ev_fore, in_ev_act, in_ev_sent, in_ev_push, cal_filter, cal_market_filter],
                outputs=[cal_action_msg, cal_info_bar, calendar_visual_feed, calendar_table]
            )

        # ═══════════════════════════════════════════════════════════
        # TAB 3: Official Regulatory Circulars & Notifications Repository
        # ═══════════════════════════════════════════════════════════
        with gr.TabItem("📜 Regulatory Circulars & Official PDFs"):
            circ_info_bar = gr.Markdown(value=init_circ_summary, elem_id="circ_info_bar", visible=False)

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
                    scale=3
                )

            with gr.Column(elem_id="sec_circ_directory", elem_classes=["epm-modular-section"]):
                with gr.Row(elem_id="circ_action_toolbar", elem_classes=["epm-toolbar-card"]):
                    circ_refresh_btn = gr.Button("🔄 Check & Poll Official Circulars (NSE, BSE, MCX, RBI, FINMIN, FOMC)", variant="primary", scale=3)
                    circ_dispatch_btn = gr.Button("📲 Forward Latest Circular to Telegram", variant="secondary", scale=2)

                circ_action_msg = gr.Markdown(elem_id="circ_action_msg")

                gr.HTML(render_table_ribbon("circ_table", "Official Regulatory Documents Directory", subtitle="Verified PDFs", count_badge="Directives", section_id="sec_circ_directory"))
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
                    datatype=["str", "str", "str", "str", "markdown", "str", "str", "markdown"],
                    value=init_circ_rows,
                    interactive=False,
                    wrap=True,
                    elem_id="circ_table"
                )

            with gr.Column(elem_id="sec_circ_visual", elem_classes=["epm-modular-section"]):
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
                    gr.Markdown("**⏰ Automated Morning Dispatches (IST Schedule):**")
                    adm_auto_weekly_pdf_fri6am = gr.Checkbox(
                        label="📑 Friday 06:00 AM IST — Auto-Dispatch Weekly Multi-Market A4 PDF Dossier (Next Week Mon–Sat)",
                        value=telegram_notifier.auto_weekly_pdf_fri_6am
                    )
                    adm_auto_monthly_pdf_25th6am = gr.Checkbox(
                        label="📑 25th of Month 06:00 AM IST — Auto-Dispatch Monthly Multi-Market A4 PDF Outlook (Upcoming Month)",
                        value=telegram_notifier.auto_monthly_pdf_25th_6am
                    )
                    adm_auto_hol_7am = gr.Checkbox(
                        label="🏖️ 07:00 AM IST — Auto-Forward Next-Day Trading Holiday Alert (1 Day Before NSE/BSE/MCX/NYSE Holiday)",
                        value=telegram_notifier.auto_holiday_7am
                    )
                    adm_auto_circulars = gr.Checkbox(
                        label="📜 Auto-Forward Critical Regulatory Circulars (NSE, BSE, MCX, RBI, FinMin, FOMC, NYSE, Crypto) with 3-5 Bullets & PDF Link",
                        value=getattr(telegram_notifier, "auto_circulars_tg", False)
                    )
                    with gr.Accordion("⚙️ Legacy Dispatches (Optional)", open=False):
                        adm_auto_today_7am = gr.Checkbox(
                            label="🌅 07:00 AM IST — Auto-Forward Today's Complete Calendar Snapshot (5 Market Messages)",
                            value=telegram_notifier.auto_daily_today_7am
                        )
                        adm_auto_tom_705am = gr.Checkbox(
                            label="🌄 07:05 AM IST — Auto-Forward Tomorrow's Lined-Up Events Snapshot (5 Market Messages)",
                            value=telegram_notifier.auto_daily_tomorrow_705am
                        )
                        adm_auto_weekly_fri7am = gr.Checkbox(
                            label="🗓️ Friday 07:00 AM IST — Auto-Forward Weekly Calendar Links (Apple & Google)",
                            value=getattr(telegram_notifier, "auto_weekly_fri_7am", False)
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
                        resend_weekly_btn = gr.Button("📲 Resend Full-Week Calendar Sync Link Now")

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
                    adm_auto_circulars, adm_auto_weekly_pdf_fri6am, adm_auto_monthly_pdf_25th6am
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
            gr.Markdown("### 📸 Omnichannel Social Media Auto-Broadcasting Hub (Instagram, X / Twitter & Discord)")
            gr.Markdown(
                "Directly publishes publication-grade **1080×1350 financial infographic cards** (Finshots/Bloomberg style) and morning multi-market calendar snapshots to **Instagram, X / Twitter, and Discord** via official APIs."
            )
            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### 📸 Instagram Integration (Meta Graph API)")
                    adm_ig_enabled = gr.Checkbox(
                        label="Enable Instagram Auto-Posting (Visual Cards & Captions)",
                        value=social_publisher.instagram_enabled
                    )
                    adm_ig_account_id = gr.Textbox(
                        label="Instagram Business / Creator Account ID",
                        value=social_publisher.instagram_account_id,
                        placeholder="e.g. 17841400000000000"
                    )
                    adm_ig_token = gr.Textbox(
                        label="Meta Graph API Access Token",
                        value=social_publisher.instagram_access_token,
                        type="password",
                        placeholder="Paste long-lived Meta Page/IG Token..."
                    )
                    test_ig_btn = gr.Button("📸 Send Test 1080×1350 Card to Instagram")

                    gr.Markdown("#### 🎮 Discord Webhook Integration")
                    adm_discord_enabled = gr.Checkbox(
                        label="Enable Discord Channel Alerts",
                        value=social_publisher.discord_enabled
                    )
                    adm_discord_webhook = gr.Textbox(
                        label="Discord Webhook URL",
                        value=social_publisher.discord_webhook_url,
                        placeholder="https://discord.com/api/webhooks/..."
                    )
                    test_discord_btn = gr.Button("🎮 Send Test Rich Embed to Discord")

                with gr.Column():
                    gr.Markdown("#### 🐦 X / Twitter API v2 (Direct Integration)")
                    adm_twitter_enabled = gr.Checkbox(
                        label="Enable X / Twitter Auto-Tweeting (Card + $Cashtags)",
                        value=social_publisher.twitter_enabled
                    )
                    adm_tw_api_key = gr.Textbox(
                        label="API Key (Consumer Key)",
                        value=social_publisher.twitter_api_key,
                        placeholder="Twitter App API Key..."
                    )
                    adm_tw_api_secret = gr.Textbox(
                        label="API Key Secret",
                        value=social_publisher.twitter_api_secret,
                        type="password",
                        placeholder="Twitter App API Key Secret..."
                    )
                    adm_tw_token = gr.Textbox(
                        label="Access Token",
                        value=social_publisher.twitter_access_token,
                        placeholder="OAuth Access Token..."
                    )
                    adm_tw_secret = gr.Textbox(
                        label="Access Token Secret",
                        value=social_publisher.twitter_access_secret,
                        type="password",
                        placeholder="OAuth Access Token Secret..."
                    )
                    adm_tw_min_score = gr.Slider(
                        minimum=5, maximum=10, step=1,
                        label="Minimum AI Score to Tweet (Recommended: 8 - Stays within 1,500/mo Free Tier)",
                        value=social_publisher.twitter_min_score
                    )
                    test_tw_btn = gr.Button("🐦 Send Test Tweet with Image Card")

                    gr.Markdown("#### 🖼️ Image-Only Visual Dispatch Mode")
                    adm_news_photos = gr.Checkbox(
                        label="Deliver News as Graphic Infographic Cards instead of plain text across Telegram & all channels",
                        value=social_publisher.send_news_as_photos
                    )
                    adm_social_pub_url = gr.Textbox(
                        label="Public Image Server URL (For Meta/Instagram to fetch card images)",
                        value=social_publisher.get_public_url(),
                        placeholder="https://p01--news-engine-service--dkhqtlpvx6bh.code.run"
                    )

            save_social_btn = gr.Button("💾 Save Omnichannel Social Media Settings", variant="primary")
            social_admin_status = gr.Markdown()

            save_social_btn.click(
                save_social_media_settings,
                inputs=[
                    adm_ig_enabled, adm_ig_account_id, adm_ig_token,
                    adm_twitter_enabled, adm_tw_api_key, adm_tw_api_secret, adm_tw_token, adm_tw_secret, adm_tw_min_score,
                    adm_discord_enabled, adm_discord_webhook,
                    adm_news_photos, adm_social_pub_url
                ],
                outputs=[social_admin_status]
            )
            test_ig_btn.click(lambda: trigger_test_social("instagram"), outputs=[social_admin_status])
            test_tw_btn.click(lambda: trigger_test_social("twitter"), outputs=[social_admin_status])
            test_discord_btn.click(lambda: trigger_test_social("discord"), outputs=[social_admin_status])

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
                        <li><span class="guide-pill">Friday 06:00 AM IST</span> &nbsp;—&nbsp; Automatically compiles and dispatches the <b>Weekly Multi-Market Snapshot PDF Dossier</b> (A4 Landscape, 14-column ledger format covering Monday to Saturday across NSE, BSE, MCX, CRYPTO & NYSE) directly into the designated Calendar Telegram channel.</li>
                        <li><span class="guide-pill">25th of Month 06:00 AM IST</span> &nbsp;—&nbsp; Automatically compiles and dispatches the <b>Monthly Multi-Market Outlook PDF Dossier</b> (A4 Landscape, weekly-sectioned ledger covering all major catalysts for the upcoming month) into the Calendar channel.</li>
                        <li><span class="guide-pill">07:00 AM IST Daily (Holiday Check)</span> &nbsp;—&nbsp; Evaluates upcoming calendar schedules 24 hours in advance and auto-forwards a <b>Next-Day Trading Holiday Alert</b> across all 5 major bourses whenever a session closure or evening trading break is detected.</li>
                        <li><span class="guide-pill">1-Click PDF Downloads</span> &nbsp;—&nbsp; Immediate access to both weekly and monthly print-ready A4 dossiers on Tab 2 or via machine endpoints <span class="guide-pill">/api/calendar/pdf/weekly</span> and <span class="guide-pill">/api/calendar/pdf/monthly</span>.</li>
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
    head=(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">'
        f"<style>{CUSTOM_CSS}</style><script>{TERMINAL_CLIENT_JS}</script>"
    ),
    js=TERMINAL_CLIENT_JS
)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
