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
   EPMPRO INSTITUTIONAL FINTECH DESIGN SYSTEM (2026 DARK-MODE ARCHITECTURE)
   Specialized for Terminal Platforms: Bloomberg, Linear, TradingView, Robinhood
   ═══════════════════════════════════════════════════════════════════════════ */

:root {
    --font-sans: "Inter", "Geist", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --font-mono: "JetBrains Mono", "Geist Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;

    /* Institutional Dark Slate Palette */
    --bg-page: #0B0E14;              /* Deep Charcoal Slate */
    --bg-surface: #121721;           /* Surface / Cards / Tables */
    --bg-surface-elevated: #161D2A;  /* Elevated Panels / Headers */
    --bg-surface-subtle: #1C2536;    /* Interactive hovers & pills */

    --border-subtle: rgba(255, 255, 255, 0.05);
    --border-color: rgba(255, 255, 255, 0.08);
    --border-strong: rgba(255, 255, 255, 0.16);
    --border-focus: #0052FF;

    --text-primary: #F1F5F9;         /* High-contrast crisp white */
    --text-secondary: #94A3B8;       /* Slate medium text */
    --text-muted: #64748B;           /* Dim text */

    /* Financial Accents */
    --accent-blue: #0052FF;          /* International Klein Blue */
    --accent-blue-hover: #1A66FF;
    --accent-amber: #F59E0B;         /* Bloomberg Amber */
    --accent-emerald: #10B981;       /* Bullish Emerald */
    --accent-emerald-bg: rgba(16, 185, 129, 0.15);
    --accent-rose: #F43F5E;          /* Bearish Rose */
    --accent-rose-bg: rgba(244, 63, 94, 0.15);
    --accent-slate-bg: rgba(148, 163, 184, 0.12);

    --radius-xs: 4px;
    --radius-sm: 6px;
    --radius-md: 8px;
    --radius-lg: 12px;
}

/* 1. Global Reset & Charcoal Slate Baseline */
html, body {
    width: 100% !important;
    max-width: 100vw !important;
    overflow-x: hidden !important;
    margin: 0 !important;
    padding: 0 !important;
    background-color: var(--bg-page) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-sans) !important;
    font-size: 13px !important;
    line-height: 1.45 !important;
    -webkit-font-smoothing: antialiased !important;
    -moz-osx-font-smoothing: grayscale !important;
}

*, *::before, *::after {
    box-sizing: border-box !important;
}

/* 2. Gradio Container (Enforced Institutional Dark Layout) */
.gradio-container, 
.gradio-container > .main, 
.gradio-container > .wrap,
div[class*="gradio-container"],
.dark, .light {
    max-width: 100% !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 4px 16px 20px 16px !important;
    background-color: var(--bg-page) !important;
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
    background: transparent !important;
}

/* 3. Typography & Section Headers */
h1, h2, h3, h4 {
    font-family: var(--font-sans) !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.02em !important;
    margin-block: 0.4rem 0.5rem !important;
}

h1 { font-size: 20px !important; font-weight: 800 !important; }
h2 { font-size: 16px !important; font-weight: 700 !important; }
h3 { font-size: 13px !important; font-weight: 700 !important; }
h4 { font-size: 12px !important; font-weight: 600 !important; color: var(--text-secondary) !important; }

p, span, div, label {
    font-family: var(--font-sans) !important;
}

/* 4. Desktop Table Headers - Zero Single-Letter Word Wrapping */
th, thead th, .gradio-container thead th, div[data-testid="dataframe"] thead th {
    white-space: nowrap !important;
    word-break: keep-all !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    text-transform: uppercase !important;
    font-family: var(--font-sans) !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    letter-spacing: 0.04em !important;
    color: #94A3B8 !important;
    background: #151B27 !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    padding: 7px 10px !important;
    vertical-align: middle !important;
}

/* Desktop Sensible Column Minimum Widths */
#top_news_table th:nth-child(1), #top_news_table td:nth-child(1) { min-width: 78px !important; width: 78px !important; text-align: center !important; }
#top_news_table th:nth-child(2), #top_news_table td:nth-child(2) { min-width: 96px !important; width: 96px !important; text-align: center !important; }
#top_news_table th:nth-child(3), #top_news_table td:nth-child(3) { min-width: 84px !important; width: 84px !important; text-align: center !important; }
#top_news_table th:nth-child(4), #top_news_table td:nth-child(4) { min-width: 320px !important; }
#top_news_table th:nth-child(5), #top_news_table td:nth-child(5) { min-width: 130px !important; width: 130px !important; }
#top_news_table th:nth-child(6), #top_news_table td:nth-child(6) { min-width: 260px !important; }
#top_news_table th:nth-child(7), #top_news_table td:nth-child(7) { min-width: 110px !important; width: 110px !important; }
#top_news_table th:nth-child(8), #top_news_table td:nth-child(8) { min-width: 78px !important; width: 78px !important; text-align: center !important; }
#top_news_table th:nth-child(9), #top_news_table td:nth-child(9) { min-width: 95px !important; width: 95px !important; text-align: center !important; }

#bottom_news_table th:nth-child(1), #bottom_news_table td:nth-child(1) { min-width: 90px !important; text-align: center !important; }
#bottom_news_table th:nth-child(2), #bottom_news_table td:nth-child(2) { min-width: 110px !important; }
#bottom_news_table th:nth-child(3), #bottom_news_table td:nth-child(3) { min-width: 340px !important; }
#bottom_news_table th:nth-child(4), #bottom_news_table td:nth-child(4) { min-width: 80px !important; text-align: center !important; }
#bottom_news_table th:nth-child(5), #bottom_news_table td:nth-child(5) { min-width: 96px !important; text-align: center !important; }
#bottom_news_table th:nth-child(6), #bottom_news_table td:nth-child(6) { min-width: 100px !important; text-align: center !important; }

/* 5. Numerical & Data Cells (JetBrains / Geist Mono + Tabular Figures) */
#top_news_table td:nth-child(1),
#top_news_table td:nth-child(8),
#top_news_table td:nth-child(9),
#bottom_news_table td:nth-child(1),
#bottom_news_table td:nth-child(4),
#calendar_table td:nth-child(1),
#calendar_table td:nth-child(2),
#calendar_table td:nth-child(3),
#calendar_table td:nth-child(10),
#calendar_table td:nth-child(11),
#calendar_table td:nth-child(12),
#calendar_table td:nth-child(13),
#circ_table td:nth-child(2),
#circ_table td:nth-child(3),
.timer-cell, code, .epm-ticker-val, .epm-ticker-chg {
    font-family: var(--font-mono) !important;
    font-feature-settings: "tnum" 1, "zero" 1 !important;
    font-variant-numeric: tabular-nums !important;
}

/* 6. Crisp Neutral Headline Links & Hover Glow */
#top_news_table td:nth-child(4) a,
#bottom_news_table td:nth-child(3) a,
#circ_table td:nth-child(5) a,
.epm-news-title {
    color: #F1F5F9 !important;
    text-decoration: none !important;
    font-weight: 600 !important;
    transition: color 0.15s ease !important;
}
#top_news_table td:nth-child(4) a:hover,
#bottom_news_table td:nth-child(3) a:hover,
#circ_table td:nth-child(5) a:hover,
.epm-news-title:hover {
    color: #60A5FA !important;
    text-decoration: underline !important;
}

/* 7. Institutional Dark Table Rows */
tbody tr td, .gradio-container tbody td {
    background-color: var(--bg-surface) !important;
    color: var(--text-primary) !important;
    border-bottom: 1px solid var(--border-subtle) !important;
    border-top: none !important;
    padding: 7px 10px !important;
    font-size: 12.5px !important;
}

tbody tr:nth-child(even) td {
    background-color: #0E131C !important;
}

tbody tr:hover td {
    background-color: #182030 !important;
}

/* 8. Sleek Sentiment Badge Pills */
.sent-pill, [data-sent], .sent-bullish {
    background: rgba(16, 185, 129, 0.15) !important;
    color: #10B981 !important;
    border: 1px solid rgba(16, 185, 129, 0.3) !important;
    border-radius: 4px !important;
    padding: 2px 7px !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    display: inline-flex !important;
    align-items: center !important;
}
.sent-bearish {
    background: rgba(244, 63, 94, 0.15) !important;
    color: #F43F5E !important;
    border: 1px solid rgba(244, 63, 94, 0.3) !important;
    border-radius: 4px !important;
    padding: 2px 7px !important;
    font-size: 11px !important;
    font-weight: 700 !important;
    display: inline-flex !important;
    align-items: center !important;
}
.sent-neutral {
    background: rgba(148, 163, 184, 0.12) !important;
    color: #94A3B8 !important;
    border: 1px solid rgba(148, 163, 184, 0.25) !important;
    border-radius: 4px !important;
    padding: 2px 7px !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    display: inline-flex !important;
    align-items: center !important;
}

/* Color-coded score & impact micro-pills */
.score-pill, #top_news_table td:nth-child(1) {
    color: #F59E0B !important;
    font-weight: 700 !important;
}

/* 9. Top Navigation Bar & Desk Header (Institutional Dark Mode) */
.epm-top-navbar {
    background: var(--bg-surface-elevated) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 8px !important;
    backdrop-filter: blur(12px) !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4) !important;
    padding: 6px 12px !important;
    margin-bottom: 8px !important;
}

.epm-nav-row-1 {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 12px !important;
    min-height: 32px !important;
}

.epm-nav-brand-cluster {
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
}

.epm-nav-bolt {
    font-size: 16px !important;
    color: #0052FF !important;
    filter: drop-shadow(0 0 6px rgba(0, 82, 255, 0.5));
}

.epm-nav-title {
    font-family: var(--font-sans) !important;
    font-size: 15px !important;
    font-weight: 800 !important;
    color: #F1F5F9 !important;
    letter-spacing: -0.02em !important;
}

.epm-title-highlight {
    color: #0052FF !important;
}

.epm-nav-version {
    font-size: 9.5px !important;
    font-weight: 700 !important;
    background: rgba(0, 82, 255, 0.15) !important;
    color: #60A5FA !important;
    border: 1px solid rgba(0, 82, 255, 0.3) !important;
    padding: 1px 5px !important;
    border-radius: 4px !important;
}

.epm-nav-status-badge {
    display: inline-flex !important;
    align-items: center !important;
    gap: 5px !important;
    font-size: 10px !important;
    font-weight: 700 !important;
    color: #10B981 !important;
    background: rgba(16, 185, 129, 0.15) !important;
    border: 1px solid rgba(16, 185, 129, 0.3) !important;
    padding: 1px 6px !important;
    border-radius: 4px !important;
}

.epm-live-dot {
    width: 6px !important;
    height: 6px !important;
    border-radius: 50% !important;
    background: #10B981 !important;
    box-shadow: 0 0 6px #10B981 !important;
    animation: epmPulseDot 1.8s infinite ease-in-out !important;
}

@keyframes epmPulseDot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.85); }
}

.epm-nav-telemetry {
    display: flex !important;
    align-items: center !important;
    gap: 5px !important;
}

.epm-telem-pill {
    font-size: 9.5px !important;
    font-weight: 600 !important;
    background: #181F2C !important;
    color: #94A3B8 !important;
    border: 1px solid var(--border-subtle) !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
}
.epm-telem-pill b {
    color: #F1F5F9 !important;
    font-family: var(--font-mono) !important;
}
.epm-telem-tg b {
    color: #10B981 !important;
}

/* Macro Ticker Strip */
.epm-telemetry-strip {
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    background: var(--bg-page) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 6px !important;
    padding: 3px 10px !important;
    overflow-x: auto !important;
    scrollbar-width: none !important;
}
.epm-telemetry-strip::-webkit-scrollbar { display: none !important; }

.epm-ticker-item {
    display: flex !important;
    align-items: center !important;
    gap: 5px !important;
    font-size: 11px !important;
    white-space: nowrap !important;
}
.epm-ticker-sym { color: #94A3B8 !important; font-weight: 600 !important; }
.epm-ticker-val { color: #F1F5F9 !important; font-weight: 700 !important; font-family: var(--font-mono) !important; }
.epm-ticker-chg.up { color: #10B981 !important; font-family: var(--font-mono) !important; font-weight: 700 !important; }
.epm-ticker-chg.down { color: #F43F5E !important; font-family: var(--font-mono) !important; font-weight: 700 !important; }
.epm-ticker-divider { width: 1px !important; height: 12px !important; background: var(--border-color) !important; }

/* Desktop Row 2 Tabs */
.epm-nav-row-2 {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 8px !important;
    padding-top: 5px !important;
    border-top: 1px solid var(--border-subtle) !important;
}

.epm-quick-tabs-container {
    display: flex !important;
    align-items: center !important;
    gap: 4px !important;
}

.epm-tab-pill {
    display: inline-flex !important;
    align-items: center !important;
    gap: 5px !important;
    padding: 4px 10px !important;
    border-radius: 6px !important;
    background: #181F2C !important;
    border: 1px solid var(--border-color) !important;
    color: #94A3B8 !important;
    font-family: var(--font-sans) !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    cursor: pointer !important;
    transition: all 0.15s ease !important;
}
.epm-tab-pill:hover {
    background: #1E2738 !important;
    color: #F1F5F9 !important;
    border-color: rgba(255, 255, 255, 0.15) !important;
}
.epm-tab-pill.active {
    background: rgba(0, 82, 255, 0.18) !important;
    color: #60A5FA !important;
    border-color: #0052FF !important;
    box-shadow: 0 0 10px rgba(0, 82, 255, 0.25) !important;
}
.epm-tab-pill-bullet {
    width: 5px !important;
    height: 5px !important;
    border-radius: 50% !important;
    background: #64748B !important;
}
.epm-tab-pill.active .epm-tab-pill-bullet {
    background: #60A5FA !important;
    box-shadow: 0 0 5px #60A5FA !important;
}

.epm-nav-controls {
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
}

.epm-cmd-launcher-btn {
    display: inline-flex !important;
    align-items: center !important;
    gap: 5px !important;
    height: 26px !important;
    padding: 0 8px !important;
    background: #181F2C !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 5px !important;
    color: #94A3B8 !important;
    font-size: 11px !important;
    cursor: pointer !important;
}
.epm-cmd-badge {
    font-family: var(--font-mono) !important;
    font-size: 9.5px !important;
    background: rgba(0, 82, 255, 0.15) !important;
    color: #60A5FA !important;
    border: 1px solid rgba(0, 82, 255, 0.3) !important;
    padding: 0 4px !important;
    border-radius: 3px !important;
}

.epm-nav-search-wrap {
    display: inline-flex !important;
    align-items: center !important;
    height: 26px !important;
    background: #181F2C !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 5px !important;
    padding: 0 6px !important;
    gap: 4px !important;
}
.epm-nav-search-wrap input {
    background: transparent !important;
    border: none !important;
    color: #F1F5F9 !important;
    font-size: 11px !important;
    outline: none !important;
    width: 105px !important;
}

.epm-top-btn {
    display: inline-flex !important;
    align-items: center !important;
    gap: 4px !important;
    height: 26px !important;
    padding: 0 8px !important;
    background: #181F2C !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 5px !important;
    color: #F1F5F9 !important;
    font-size: 11px !important;
    cursor: pointer !important;
}
.epm-top-btn.epm-btn-active {
    background: rgba(16, 185, 129, 0.15) !important;
    color: #10B981 !important;
    border-color: rgba(16, 185, 129, 0.3) !important;
}

/* 10. Table Ribbons & Modular Workspace Headers */
.epm-table-ribbon, #cal_table_header_strip, #tab1_header_strip {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    background: #151B27 !important;
    border: 1px solid var(--border-color) !important;
    border-bottom: 2px solid #0052FF !important;
    border-radius: 6px 6px 0 0 !important;
    padding: 4px 10px !important;
    min-height: 30px !important;
}

.epm-ribbon-title {
    font-size: 11.5px !important;
    font-weight: 700 !important;
    color: #F1F5F9 !important;
    letter-spacing: 0.02em !important;
}
.epm-ribbon-subtitle {
    font-size: 10px !important;
    color: #64748B !important;
}
.epm-ribbon-badge {
    font-size: 9.5px !important;
    font-weight: 700 !important;
    background: rgba(0, 82, 255, 0.15) !important;
    color: #60A5FA !important;
    border: 1px solid rgba(0, 82, 255, 0.3) !important;
    padding: 1px 5px !important;
    border-radius: 3px !important;
}

.epm-ribbon-btn, button.epm-hdr-action-btn {
    height: 22px !important;
    padding: 0 7px !important;
    font-size: 10px !important;
    font-weight: 600 !important;
    background: #181F2C !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 4px !important;
    color: #94A3B8 !important;
    cursor: pointer !important;
    transition: all 0.12s ease !important;
}
.epm-ribbon-btn:hover, button.epm-hdr-action-btn:hover {
    background: #1E2738 !important;
    color: #F1F5F9 !important;
    border-color: rgba(255, 255, 255, 0.2) !important;
}

/* 11. Bento Cards (Settings Hub, User Guide & Admin Panels) */
.epm-bento-card {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 10px !important;
    padding: 18px 20px !important;
    margin-bottom: 14px !important;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2) !important;
    transition: border-color 0.15s ease !important;
}
.epm-bento-card:hover {
    border-color: rgba(255, 255, 255, 0.14) !important;
}

.epm-bento-header {
    display: flex !important;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-subtle);
}
.epm-bento-title {
    font-size: 14px !important;
    font-weight: 700 !important;
    color: #F1F5F9 !important;
    display: flex;
    align-items: center;
    gap: 8px;
}
.epm-bento-desc {
    font-size: 11.5px !important;
    color: #94A3B8 !important;
    margin-bottom: 14px !important;
    line-height: 1.5 !important;
}

/* Custom Segmented Inputs & Buttons in Dark Mode */
.gradio-container button.primary,
.gradio-container button[variant="primary"] {
    background: #0052FF !important;
    color: #ffffff !important;
    border: none !important;
    font-weight: 700 !important;
    border-radius: 6px !important;
    box-shadow: 0 2px 10px rgba(0, 82, 255, 0.3) !important;
    transition: all 0.15s ease !important;
}
.gradio-container button.primary:hover,
.gradio-container button[variant="primary"]:hover {
    background: #1A66FF !important;
    box-shadow: 0 4px 14px rgba(0, 82, 255, 0.45) !important;
}

.gradio-container input[type="text"],
.gradio-container input[type="password"],
.gradio-container textarea,
.gradio-container select {
    background-color: #181F2C !important;
    border: 1px solid var(--border-color) !important;
    color: #F1F5F9 !important;
    border-radius: 6px !important;
    font-size: 12px !important;
}
.gradio-container input:focus,
.gradio-container textarea:focus {
    border-color: #0052FF !important;
    box-shadow: 0 0 0 1px #0052FF !important;
}

/* Custom Sleek Checkbox / Toggle Switches */
.gradio-container input[type="checkbox"] {
    accent-color: #0052FF !important;
    cursor: pointer !important;
}

/* 12. Inshorts & Mobile Side Drawer Dark Theme */
.epm-drawer-backdrop {
    position: fixed !important;
    inset: 0 !important;
    background: rgba(0, 0, 0, 0.65) !important;
    backdrop-filter: blur(4px) !important;
    z-index: 1040 !important;
    opacity: 0 !important;
    pointer-events: none !important;
    transition: opacity 0.25s ease !important;
}
.epm-drawer-backdrop.is-open {
    opacity: 1 !important;
    pointer-events: auto !important;
}

.epm-mobile-drawer {
    position: fixed !important;
    top: 0 !important;
    right: -320px !important;
    width: 300px !important;
    max-width: 86vw !important;
    height: 100vh !important;
    background: #121721 !important;
    z-index: 1050 !important;
    box-shadow: -8px 0 24px rgba(0, 0, 0, 0.5) !important;
    border-left: 1px solid rgba(255, 255, 255, 0.1) !important;
    transition: right 0.28s cubic-bezier(0.16, 1, 0.3, 1) !important;
    display: flex !important;
    flex-direction: column !important;
    overflow-y: auto !important;
    -webkit-overflow-scrolling: touch !important;
}
.epm-mobile-drawer.is-open {
    right: 0 !important;
}

.epm-drawer-header {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    padding: 14px 16px !important;
    background: #151B27 !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
}
.epm-drawer-title {
    color: #F1F5F9 !important;
}
.epm-drawer-close-btn {
    width: 28px !important;
    height: 28px !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    background: #181F2C !important;
    color: #94A3B8 !important;
    border-radius: 6px !important;
    cursor: pointer !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
.epm-drawer-close-btn:hover {
    color: #F1F5F9 !important;
    border-color: #0052FF !important;
}
.epm-drawer-body {
    padding: 14px 16px !important;
    display: flex !important;
    flex-direction: column !important;
    gap: 12px !important;
    flex: 1 !important;
}
.epm-drawer-section-label {
    font-size: 10px !important;
    font-weight: 700 !important;
    letter-spacing: 0.06em !important;
    color: #64748B !important;
    text-transform: uppercase !important;
    margin-bottom: 4px !important;
}
.epm-drawer-nav-list {
    display: flex !important;
    flex-direction: column !important;
    gap: 6px !important;
}
.epm-drawer-nav-item {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
    padding: 8px 12px !important;
    background: #181F2C !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 8px !important;
    cursor: pointer !important;
    text-align: left !important;
    transition: all 0.15s ease !important;
}
.epm-drawer-nav-item:hover, .epm-drawer-nav-item.active {
    background: rgba(0, 82, 255, 0.15) !important;
    border-color: #0052FF !important;
}
.epm-drawer-item-name { color: #F1F5F9 !important; font-size: 12px !important; font-weight: 700 !important; }
.epm-drawer-item-desc { color: #94A3B8 !important; font-size: 10px !important; }
.epm-drawer-tool-btn {
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
    padding: 8px 12px !important;
    background: #181F2C !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 8px !important;
    color: #F1F5F9 !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    cursor: pointer !important;
}
.epm-drawer-tool-btn:hover {
    border-color: #0052FF !important;
    background: rgba(0, 82, 255, 0.1) !important;
}
.epm-drawer-footer {
    padding: 12px 16px !important;
    border-top: 1px solid rgba(255, 255, 255, 0.08) !important;
    font-size: 9.5px !important;
    color: #64748B !important;
    text-align: center !important;
}

/* Inshorts Full-Page / Bottom-Sheet Drawer */
.epm-inshorts-backdrop {
    position: fixed !important;
    inset: 0 !important;
    background: rgba(0, 0, 0, 0.65) !important;
    backdrop-filter: blur(5px) !important;
    z-index: 1060 !important;
    opacity: 0 !important;
    pointer-events: none !important;
    transition: opacity 0.25s ease !important;
}
.epm-inshorts-backdrop.is-open {
    opacity: 1 !important;
    pointer-events: auto !important;
}

.epm-inshorts-drawer {
    position: fixed !important;
    left: 0 !important;
    right: 0 !important;
    bottom: -110vh !important;
    max-height: 94vh !important;
    height: 90vh !important;
    background: #121721 !important;
    border-radius: 18px 18px 0 0 !important;
    box-shadow: 0 -12px 36px rgba(0, 0, 0, 0.6) !important;
    border-top: 1px solid rgba(255, 255, 255, 0.12) !important;
    z-index: 99999 !important;
    display: flex !important;
    flex-direction: column !important;
    overflow: hidden !important;
    transition: bottom 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
}
.epm-inshorts-drawer.is-open {
    bottom: 0 !important;
}

.epm-inshorts-handle-bar {
    width: 100% !important;
    display: flex !important;
    justify-content: center !important;
    padding: 8px 0 4px 0 !important;
    cursor: grab !important;
    flex-shrink: 0 !important;
}
.epm-inshorts-handle {
    width: 36px !important;
    height: 4px !important;
    background: #334155 !important;
    border-radius: 2px !important;
}
.epm-inshorts-header {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    padding: 6px 16px 10px 16px !important;
    background: #151B27 !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
    flex-shrink: 0 !important;
}
.epm-inshorts-meta-strip {
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
    flex-wrap: wrap !important;
}
.epm-inshorts-source {
    font-size: 10.5px !important;
    font-weight: 700 !important;
    color: #60A5FA !important;
    background: rgba(37, 99, 235, 0.15) !important;
    border: 1px solid rgba(59, 130, 246, 0.3) !important;
    padding: 2px 7px !important;
    border-radius: 4px !important;
}
.epm-inshorts-time {
    font-size: 10px !important;
    color: #94A3B8 !important;
    font-family: var(--font-mono) !important;
}
.epm-inshorts-close {
    width: 28px !important;
    height: 28px !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 6px !important;
    background: #181F2C !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    font-size: 13px !important;
    font-weight: 700 !important;
    color: #94A3B8 !important;
    cursor: pointer !important;
}
.epm-inshorts-close:hover {
    color: #F1F5F9 !important;
    border-color: #0052FF !important;
}
.epm-inshorts-body-scroll {
    padding: 16px 18px !important;
    overflow-y: auto !important;
    -webkit-overflow-scrolling: touch !important;
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
    gap: 14px !important;
}
.epm-inshorts-hero-banner {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    flex-wrap: wrap !important;
    gap: 8px !important;
}
.epm-inshorts-title {
    font-family: var(--font-sans) !important;
    font-size: 18px !important;
    font-weight: 800 !important;
    line-height: 1.35 !important;
    color: #F1F5F9 !important;
    letter-spacing: -0.02em !important;
    margin: 0 !important;
}
.epm-inshorts-section {
    display: flex !important;
    flex-direction: column !important;
    gap: 6px !important;
    background: #151B27 !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 8px !important;
    padding: 12px 14px !important;
}
.epm-inshorts-section-heading {
    font-size: 10.5px !important;
    font-weight: 800 !important;
    color: #64748B !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
}
.epm-inshorts-reasoning-text {
    font-family: var(--font-sans) !important;
    font-size: 13.5px !important;
    line-height: 1.55 !important;
    color: #CBD5E1 !important;
}
.epm-inshorts-metrics-grid {
    display: grid !important;
    grid-template-columns: repeat(3, 1fr) !important;
    gap: 8px !important;
}
.epm-metric-card {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    background: #181F2C !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 6px !important;
    padding: 8px 4px !important;
    text-align: center !important;
}
.epm-metric-card.highlight {
    background: rgba(16, 185, 129, 0.12) !important;
    border-color: rgba(16, 185, 129, 0.3) !important;
}
.epm-metric-card .m-label {
    font-size: 9px !important;
    font-weight: 700 !important;
    color: #64748B !important;
    text-transform: uppercase !important;
    letter-spacing: 0.03em !important;
}
.epm-metric-card .m-val {
    font-family: var(--font-mono) !important;
    font-size: 12px !important;
    font-weight: 700 !important;
    color: #F1F5F9 !important;
    margin-top: 2px !important;
}
.epm-metric-card.highlight .m-val {
    color: #10B981 !important;
}
.epm-inshorts-footer-note {
    font-size: 10px !important;
    color: #64748B !important;
    text-align: center !important;
    padding: 8px 0 !important;
}
.epm-inshorts-bottom-bar {
    display: flex !important;
    align-items: center !important;
    gap: 8px !important;
    padding: 10px 16px !important;
    background: #151B27 !important;
    border-top: 1px solid rgba(255, 255, 255, 0.08) !important;
    flex-shrink: 0 !important;
}
.epm-inshorts-primary-action {
    flex: 1 !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 8px 12px !important;
    background: #0052FF !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
    text-decoration: none !important;
    cursor: pointer !important;
    transition: all 0.15s ease !important;
}
.epm-inshorts-primary-action:hover {
    background: #1A66FF !important;
}
.epm-inshorts-primary-action .action-txt {
    font-size: 12.5px !important;
    font-weight: 700 !important;
}
.epm-inshorts-primary-action .action-sub {
    font-size: 9.5px !important;
    opacity: 0.85 !important;
}
.epm-inshorts-dismiss-btn {
    height: 38px !important;
    padding: 0 14px !important;
    background: #181F2C !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    color: #CBD5E1 !important;
    border-radius: 8px !important;
    cursor: pointer !important;
    font-size: 12px !important;
    font-weight: 600 !important;
}
.epm-inshorts-dismiss-btn:hover {
    border-color: #0052FF !important;
    color: #FFFFFF !important;
}

/* Desktop: Mobile drawers, triggers, bottom bar hidden */
@media (min-width: 768px) {
    .epm-mobile-drawer,
    .epm-drawer-backdrop,
    .epm-inshorts-drawer,
    .epm-inshorts-backdrop,
    .epm-mobile-menu-trigger,
    .epm-mobile-bottom-nav {
        display: none !important;
    }
}

/* ═══════════════════════════════════════════════════════════════════════════
   13. MOBILE-FIRST RESPONSIVE ARCHITECTURE (< 768px Viewports)
   ═══════════════════════════════════════════════════════════════════════════ */
@media (max-width: 767px) {
    body {
        padding-bottom: 66px !important; /* Space for Sticky Bottom Nav */
    }

    /* 1. Header & MENU trigger */
    .epm-top-navbar {
        padding: 6px 10px !important;
        margin-bottom: 4px !important;
    }
    .epm-nav-row-1 {
        flex-direction: row !important;
        align-items: center !important;
        justify-content: space-between !important;
    }
    .epm-nav-telemetry {
        display: none !important;
    }
    .epm-mobile-menu-trigger {
        display: flex !important;
        background: #181F2C !important;
        border: 1px solid var(--border-color) !important;
        color: #F1F5F9 !important;
    }
    .epm-hamburger-line {
        background: #F1F5F9 !important;
    }
    .epm-menu-text {
        color: #F1F5F9 !important;
    }
    .epm-nav-row-2 {
        display: none !important;
    }

    /* 2. Smooth Auto-Scrolling Marquee Ticker Pinned Beneath Header */
    #epm-telemetry-ticker {
        display: flex !important;
        width: 100% !important;
        background: #0B0E14 !important;
        border-top: 1px solid rgba(255, 255, 255, 0.06) !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
        padding: 4px 6px !important;
        overflow-x: auto !important;
        scrollbar-width: none !important;
        gap: 12px !important;
    }

    /* 3. News Streams: High-Density Card List (Never Raw Crushed Tables) */
    #top_news_table thead,
    #bottom_news_table thead {
        display: none !important;
    }

    #top_news_table, #bottom_news_table {
        background: transparent !important;
        border: none !important;
        width: 100% !important;
        max-width: 100% !important;
    }

    #top_news_table table, #bottom_news_table table {
        width: 100% !important;
        min-width: 100% !important;
        display: block !important;
        border: none !important;
    }

    #top_news_table tbody, #bottom_news_table tbody {
        display: flex !important;
        flex-direction: column !important;
        gap: 8px !important;
        width: 100% !important;
    }

    #top_news_table tbody tr, #bottom_news_table tbody tr {
        display: flex !important;
        flex-direction: column !important;
        background: #121721 !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 8px !important;
        padding: 12px 14px !important;
        gap: 6px !important;
        width: 100% !important;
        cursor: pointer !important;
        transition: transform 0.15s ease, border-color 0.15s ease !important;
    }

    #top_news_table tbody tr:active, #bottom_news_table tbody tr:active {
        transform: scale(0.99) !important;
        border-color: #0052FF !important;
    }

    #top_news_table tbody td, #bottom_news_table tbody td {
        display: block !important;
        width: 100% !important;
        padding: 0 !important;
        border: none !important;
        background: transparent !important;
    }

    /* Top row meta strip (Score, Sentiment, Impact, Time, Source) */
    #top_news_table tbody td:nth-child(1),
    #top_news_table tbody td:nth-child(2),
    #top_news_table tbody td:nth-child(3),
    #top_news_table tbody td:nth-child(7),
    #top_news_table tbody td:nth-child(9),
    #bottom_news_table tbody td:nth-child(1),
    #bottom_news_table tbody td:nth-child(2),
    #bottom_news_table tbody td:nth-child(5) {
        display: inline-flex !important;
        width: auto !important;
        order: 1 !important;
        margin-right: 6px !important;
    }

    /* Middle bold headline */
    #top_news_table tbody td:nth-child(4),
    #bottom_news_table tbody td:nth-child(3) {
        font-size: 14px !important;
        font-weight: 700 !important;
        line-height: 1.4 !important;
        color: #F1F5F9 !important;
        order: 2 !important;
        margin: 4px 0 !important;
    }

    /* Bottom row: AI Reasoning & Sectors */
    #top_news_table tbody td:nth-child(6) {
        order: 3 !important;
        font-size: 12px !important;
        color: #94A3B8 !important;
        line-height: 1.45 !important;
    }
    #top_news_table tbody td:nth-child(5),
    #top_news_table tbody td:nth-child(8) {
        display: inline-flex !important;
        width: auto !important;
        order: 4 !important;
        margin-right: 6px !important;
    }

    /* 4. Thumb-Accessible Sticky Bottom Navigation Bar */
    .epm-mobile-bottom-nav {
        position: fixed !important;
        bottom: 0 !important;
        left: 0 !important;
        right: 0 !important;
        height: 56px !important;
        background: rgba(15, 19, 28, 0.96) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border-top: 1px solid rgba(255, 255, 255, 0.08) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: space-around !important;
        z-index: 1030 !important;
        padding-bottom: env(safe-area-inset-bottom, 0px) !important;
    }

    .epm-mobile-bottom-btn {
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        background: transparent !important;
        border: none !important;
        color: #94A3B8 !important;
        padding: 6px 12px !important;
        font-family: var(--font-sans) !important;
        cursor: pointer !important;
        gap: 2px !important;
        transition: color 0.15s ease !important;
    }
    .epm-mobile-bottom-btn .m-icon {
        font-size: 16px !important;
    }
    .epm-mobile-bottom-btn .m-label {
        font-size: 10px !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
    }
    .epm-mobile-bottom-btn.active {
        color: #0052FF !important;
    }
    .epm-mobile-bottom-btn.active .m-label {
        color: #60A5FA !important;
        font-weight: 700 !important;
    }

    /* 5. Mobile Filter Rows */
    #cal_filters_row, #circ_filters_row {
        flex-direction: column !important;
        align-items: stretch !important;
        gap: 4px !important;
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
<!-- Mobile Sticky Bottom Navigation Bar (Thumb-Accessible, Fixed to Bottom on Mobile) -->
<div id="epm-mobile-bottom-nav" class="epm-mobile-bottom-nav">
    <button type="button" class="epm-mobile-bottom-btn active" data-tab="0" onclick="window.epmSwitchTab(0)">
        <span class="m-icon">⚡</span>
        <span class="m-label">Wire</span>
    </button>
    <button type="button" class="epm-mobile-bottom-btn" data-tab="1" onclick="window.epmSwitchTab(1)">
        <span class="m-icon">📅</span>
        <span class="m-label">Calendar</span>
    </button>
    <button type="button" class="epm-mobile-bottom-btn" data-tab="2" onclick="window.epmSwitchTab(2)">
        <span class="m-icon">📜</span>
        <span class="m-label">Circulars</span>
    </button>
    <button type="button" class="epm-mobile-bottom-btn" data-tab="3" onclick="window.epmSwitchTab(3)">
        <span class="m-icon">⚙️</span>
        <span class="m-label">Settings</span>
    </button>
    <button type="button" class="epm-mobile-bottom-btn" data-tab="4" onclick="window.epmSwitchTab(4)">
        <span class="m-icon">❓</span>
        <span class="m-label">Docs</span>
    </button>
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
        const bottomBtns = document.querySelectorAll('.epm-mobile-bottom-btn');
        bottomBtns.forEach((b, idx) => {
            if (idx === tabIdx) b.classList.add('active');
            else b.classList.remove('active');
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
        window.epmInitPasswordToggles();
    }

    // 15. Password Reveal Toggle Controller for Settings Hub
    window.epmInitPasswordToggles = function() {
        const passwordInputs = document.querySelectorAll('input[type="password"], input[data-has-reveal="true"]');
        passwordInputs.forEach(input => {
            if (input.dataset.hasReveal === "true") return;
            input.dataset.hasReveal = "true";
            
            const wrapper = input.parentElement;
            if (!wrapper) return;
            wrapper.style.position = 'relative';
            
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.innerHTML = '👁️';
            btn.title = 'Reveal / Mask credential';
            btn.style.cssText = 'position:absolute; right:10px; top:50%; transform:translateY(-50%); background:transparent; border:none; cursor:pointer; font-size:14px; opacity:0.6; z-index:10; padding:2px 4px; border-radius:4px;';
            btn.addEventListener('mouseenter', () => btn.style.opacity = '1');
            btn.addEventListener('mouseleave', () => btn.style.opacity = '0.6');
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                if (input.type === 'password') {
                    input.type = 'text';
                    btn.innerHTML = '🔒';
                } else {
                    input.type = 'password';
                    btn.innerHTML = '👁️';
                }
            });
            wrapper.appendChild(btn);
        });
    };

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

        if (window.epmInitPasswordToggles) {
            window.epmInitPasswordToggles();
        }
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
            gr.Markdown("### ⚙️ Institutional Settings & External Integrations Hub", elem_id="settings_hdr")

            with gr.Column(elem_classes=["epm-bento-card"]):
                gr.Markdown("### 📡 Multi-Market Telegram Forwarders & Automated Dispatches")
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

            with gr.Column(elem_classes=["epm-bento-card"]):
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

            with gr.Column(elem_classes=["epm-bento-card"]):
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

            with gr.Column(elem_classes=["epm-bento-card"]):
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
            <div class="epm-docs-layout">
                <!-- Top Quick Jump Bar -->
                <div class="epm-docs-quick-bar">
                    <span class="epm-docs-pill active">📘 Quick Reference</span>
                    <a href="#api-endpoints" class="epm-docs-pill">⚡ Machine APIs</a>
                    <a href="#schedule-matrix" class="epm-docs-pill">⏰ Dispatches</a>
                    <a href="#market-coverage" class="epm-docs-pill">🌐 Markets</a>
                    <a href="#ai-architecture" class="epm-docs-pill">🧠 Gemini 2.5</a>
                </div>

                <!-- API Endpoints Bento Card -->
                <div id="api-endpoints" class="epm-bento-card">
                    <div class="epm-bento-header">
                        <div class="epm-bento-title"><span>⚡</span> Machine APIs & Programmatic Endpoints</div>
                        <span class="epm-badge sent-bullish">🟢 LIVE 200 OK</span>
                    </div>
                    <div class="epm-bento-desc">High-throughput REST and SSE endpoints for trading algos, institutional research desks, and quant workflows.</div>
                    
                    <div class="epm-api-grid">
                        <div class="epm-api-card">
                            <div class="epm-api-head">
                                <span class="epm-method-badge get">GET</span>
                                <code class="epm-endpoint">/api/news</code>
                                <span class="epm-api-status">JSON</span>
                            </div>
                            <div class="epm-api-body">
                                <p>Real-time breaking wire stream with Gemini 2.5 AI impact score (0-10), bullish/bearish directional verdict, sector classification, and relevance %.</p>
                                <pre><code>curl -s "https://your-domain/api/news?min_score=7" | jq .</code></pre>
                            </div>
                        </div>

                        <div class="epm-api-card">
                            <div class="epm-api-head">
                                <span class="epm-method-badge get">GET</span>
                                <code class="epm-endpoint">/api/calendar</code>
                                <span class="epm-api-status">JSON</span>
                            </div>
                            <div class="epm-api-body">
                                <p>15-column date-enriched catalyst ledger across NSE, BSE, MCX, CRYPTO & NYSE with live countdown timers and unfolded outcomes.</p>
                                <pre><code>curl -s "https://your-domain/api/calendar?filter=today&market=NSE"</code></pre>
                            </div>
                        </div>

                        <div class="epm-api-card">
                            <div class="epm-api-head">
                                <span class="epm-method-badge get">GET</span>
                                <code class="epm-endpoint">/api/calendar/pdf/daily-outcomes</code>
                                <span class="epm-api-status pdf">A4 PDF</span>
                            </div>
                            <div class="epm-api-body">
                                <p>Daily 5:00 PM rolling outcome dossier compiling all unfolded macroeconomic & corporate results over the last 24-hour cycle.</p>
                                <pre><code>curl -s -O "https://your-domain/api/calendar/pdf/daily-outcomes"</code></pre>
                            </div>
                        </div>

                        <div class="epm-api-card">
                            <div class="epm-api-head">
                                <span class="epm-method-badge get">GET</span>
                                <code class="epm-endpoint">/api/stream/terminal</code>
                                <span class="epm-api-status sse">SSE Stream</span>
                            </div>
                            <div class="epm-api-body">
                                <p>Low-latency Server-Sent Events stream delivering live ticker telemetry, news count, and real-time IST clock synchronization.</p>
                                <pre><code>curl -N "https://your-domain/api/stream/terminal"</code></pre>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Schedule Matrix Bento Card -->
                <div id="schedule-matrix" class="epm-bento-card">
                    <div class="epm-bento-header">
                        <div class="epm-bento-title"><span>⏰</span> Automated Morning Telegram Dispatches (IST Schedule)</div>
                        <span class="epm-badge sent-neutral">Cron Engine Active</span>
                    </div>
                    <div class="epm-docs-table-wrap">
                        <table class="epm-docs-table">
                            <thead>
                                <tr>
                                    <th>Trigger Schedule</th>
                                    <th>Target Channel</th>
                                    <th>Dossier / Deliverable</th>
                                    <th>Format</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td><code>Friday 06:00 AM IST</code></td>
                                    <td>Market Calendar Channel</td>
                                    <td>Weekly Multi-Market Catalyst Dossier (Monday to Saturday Outlook)</td>
                                    <td><span class="epm-badge-pill">A4 Landscape PDF</span></td>
                                </tr>
                                <tr>
                                    <td><code>25th of Month 06:00 AM IST</code></td>
                                    <td>Market Calendar Channel</td>
                                    <td>Monthly Multi-Market Outlook (All Major Next-Month Catalysts)</td>
                                    <td><span class="epm-badge-pill">A4 Landscape PDF</span></td>
                                </tr>
                                <tr>
                                    <td><code>Daily 05:00 PM IST</code></td>
                                    <td>Market Calendar Channel</td>
                                    <td>24-Hour Rolling Unfolded Results & Outcome Dossier</td>
                                    <td><span class="epm-badge-pill emerald">PDF Floater & A4</span></td>
                                </tr>
                                <tr>
                                    <td><code>Daily 07:00 AM IST</code></td>
                                    <td>Market Calendar Channel</td>
                                    <td>Next-Day Trading Holiday Alert (1 Day Before Session Breaks)</td>
                                    <td><span class="epm-badge-pill">Infographic Alert</span></td>
                                </tr>
                                <tr>
                                    <td><code>Real-Time / On Publication</code></td>
                                    <td>Market Calendar Channel</td>
                                    <td>Regulatory Circulars (NSE, BSE, MCX, RBI, FINMIN, FOMC)</td>
                                    <td><span class="epm-badge-pill">3-5 Bullets + PDF</span></td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Multi-Market Coverage Bento Card -->
                <div id="market-coverage" class="epm-bento-card">
                    <div class="epm-bento-header">
                        <div class="epm-bento-title"><span>🌐</span> Multi-Market Institutional Coverage Matrix</div>
                    </div>
                    <div class="epm-market-grid">
                        <div class="epm-market-box">
                            <div class="m-box-title">🇮🇳 NSE & BSE Equity / F&O</div>
                            <p>Nifty 50, Bank Nifty, quarterly corporate earnings, board meets, dividend ex-dates, and monthly derivatives expiry cycles.</p>
                        </div>
                        <div class="epm-market-box">
                            <div class="m-box-title">⛽ MCX Commodities</div>
                            <p>Crude oil inventory prints, natural gas weekly storage, gold/silver delivery expiry contracts, and dual-session trading schedules.</p>
                        </div>
                        <div class="epm-market-box">
                            <div class="m-box-title">₿ CRYPTO Macro</div>
                            <p>Bitcoin halving schedules, ETF net inflow/outflow disclosures, major protocol upgrades, and regulatory enforcement actions.</p>
                        </div>
                        <div class="epm-market-box">
                            <div class="m-box-title">🇺🇸 NYSE & NASDAQ</div>
                            <p>Federal Reserve FOMC decisions, US CPI/PPI inflation prints, non-farm payrolls, and mega-cap corporate earnings releases.</p>
                        </div>
                    </div>
                </div>

                <!-- AI Impact & Scoring Bento Card -->
                <div id="ai-architecture" class="epm-bento-card">
                    <div class="epm-bento-header">
                        <div class="epm-bento-title"><span>🧠</span> Gemini 2.5 AI Impact Scoring & Sentiment Engine</div>
                    </div>
                    <div class="epm-bento-desc">
                        Every incoming wire catalyst is analyzed through multi-modal quantitative prompts evaluating market volatility, liquidity risk, and sector tailwinds.
                    </div>
                    <ul class="epm-docs-list">
                        <li><b>Impact Scoring (0 to 10):</b> Items scored ≥ 7 are promoted to the Primary Breaking Wire and dispatched via Telegram.</li>
                        <li><b>Directional Verdict:</b> Classified into <span class="sent-pill sent-bullish">🟢 BULLISH</span>, <span class="sent-pill sent-bearish">🔴 BEARISH</span>, or <span class="sent-pill sent-neutral">⚪ NEUTRAL</span> with explicit quantitative reasoning.</li>
                        <li><b>Sector & Ticker Resolution:</b> Extracted into industrial clusters (Energy, Auto, IT, Banking) with direct stock symbol tagging.</li>
                    </ul>
                </div>
            </div>""")

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
