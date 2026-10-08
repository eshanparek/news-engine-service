import os
import time
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
from calendar_engine import calendar_engine, now_ist

# 1. Start Background Scraper, Scorer & Calendar Timer Daemons
news_worker.start()
calendar_engine.start()

# 2. FastAPI Machine-to-Machine Endpoints
app = FastAPI(
    title="EPM Pro Live News & Market Calendar Engine",
    description="Decoupled high-speed real-time news scraping, AI impact evaluation, Market Calendar countdowns, linked outcomes, and multi-channel Telegram/WhatsApp alerts.",
    version="2.0.0"
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

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": now_ist().isoformat(),
        "cached_news": len(news_worker.news_cache),
        "calendar_events": len(calendar_engine.events)
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
def get_calendar(range_filter: str = Query("all", alias="range")):
    events = calendar_engine.get_enriched_events(filter_range=range_filter)
    return {
        "status": "success",
        "as_of_ist": now_ist().strftime("%Y-%m-%d %H:%M:%S IST"),
        "count": len(events),
        "events": events
    }

@app.get("/api/calendar/unified")
def get_unified_calendar():
    """Unified endpoint compatible with Trading Terminal v34_core.js and external clients."""
    holidays = calendar_engine.get_holiday_snapshot()
    events = calendar_engine.get_enriched_events(filter_range="all")
    corporate_formatted = []
    for e in events:
        outcome_str = f"Prev: {e['previous']} | Est: {e['forecast']} → Actual: {e['actual']} ({e['outcome_sentiment']})"
        if e.get("linked_news_title"):
            outcome_str += f" | 🔗 {e['linked_news_title']}"
        corporate_formatted.append({
            "id": e["id"],
            "symbol": e["symbol"],
            "event": f"{e['event']} [{e['timer']}]",
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

@app.get("/api/calendar/ics", response_class=PlainTextResponse)
def download_calendar_ics():
    """iCal (.ics) subscription endpoint for Google Calendar, Apple Calendar & Outlook."""
    ics_content = calendar_engine.export_ical_ics()
    return PlainTextResponse(content=ics_content, media_type="text/calendar")

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
        "calendar_enabled": telegram_notifier.calendar_enabled,
        "calendar_configured": telegram_notifier.is_calendar_configured(),
        "alert_on_countdown": telegram_notifier.alert_on_countdown,
        "alert_on_outcome": telegram_notifier.alert_on_outcome,
        "alert_on_linked_news": telegram_notifier.alert_on_linked_news
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
        alert_on_linked_news=bool(cfg.alert_on_linked_news)
    )
    return {"status": "saved", "settings": saved}


# ─── 3. Gradio Web Interface Functions ───────────────────────────────────────

def get_dashboard_tables():
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
        reasoning = it.get("ai_reasoning", "")
        time_str = str(it.get("timestamp", ""))[:19]
        source = it.get("source", "")
        title = it.get("title", "")
        link = it.get("link", "#")

        if relevance >= 40 or score >= 7 or impact == "HIGH":
            top_rows.append([
                f"{score}/10",
                sent_badge,
                impact,
                title,
                sectors,
                reasoning,
                source,
                f"{relevance}%",
                time_str
            ])
        else:
            bottom_rows.append([
                time_str,
                source,
                title,
                f"{relevance}%",
                sent_badge,
                link
            ])

    if not top_rows:
        top_rows.append(["-", "⚪ Evaluating...", "-", "Evaluating live stream with Gemini 2.5...", "-", "Please wait a moment...", "-", "-", "-"])

    if not bottom_rows:
        bottom_rows.append(["-", "-", "No general news items in cache", "-", "-", "-"])

    cal_status = "🟢 Configured" if telegram_notifier.is_calendar_configured() else "⚠️ Set Calendar Chat ID in Tab 3"
    status_str = (
        f"🟢 **Engine Status:** Online | **Cached News:** {len(items)} | "
        f"**Calendar Events:** {len(calendar_engine.events)} | "
        f"**Calendar TG Channel:** {cal_status} | "
        f"**IST Clock:** {now_ist().strftime('%H:%M:%S IST')}"
    )
    return status_str, top_rows, bottom_rows

def get_calendar_tables(range_filter: str = "all"):
    events = calendar_engine.get_enriched_events(filter_range=range_filter)
    cal_rows = []
    for ev in events:
        impact = ev.get("impact", "HIGH")
        imp_badge = "🔥 HIGH" if impact == "HIGH" else ("⚡ MEDIUM" if impact == "MEDIUM" else "💤 LOW")
        linked_info = ev.get("linked_news_title", "")
        if linked_info:
            linked_display = f"🔗 {linked_info[:65]}..." if len(linked_info) > 65 else f"🔗 {linked_info}"
        else:
            linked_display = "—"

        cal_rows.append([
            ev.get("id", ""),
            ev.get("date", ""),
            f"{ev.get('time', '')} IST",
            ev.get("timer", ""),
            ev.get("symbol", ""),
            ev.get("event", ""),
            imp_badge,
            ev.get("previous", "—"),
            ev.get("forecast", "—"),
            ev.get("actual", "⏳ Pending"),
            ev.get("outcome_sentiment", "⏳ PENDING"),
            linked_display
        ])

    if not cal_rows:
        cal_rows.append(["-", "-", "-", "-", "-", "No events for selected filter", "-", "-", "-", "-", "-", "-"])

    holidays_data = calendar_engine.get_holiday_snapshot().get("comparison", [])
    hol_rows = []
    for h in holidays_data:
        hol_rows.append([
            h.get("date", ""),
            h.get("day", ""),
            h.get("description", ""),
            h.get("nse_status", ""),
            h.get("mcx_status", "")
        ])

    cal_summary = (
        f"📅 **Active Calendar Events:** {len(events)} | "
        f"**Current IST Time:** `{now_ist().strftime('%Y-%m-%d %H:%M:%S IST')}` | "
        f"**Last Sync:** `{calendar_engine.last_sync_time.strftime('%H:%M:%S IST') if calendar_engine.last_sync_time else 'Just now'}` | "
        f"**iCal Sync Feed:** `/api/calendar/ics`  |  **JSON Sync API:** `/api/calendar/unified`"
    )
    return cal_summary, cal_rows, hol_rows

def sync_and_refresh_calendar(range_filter: str):
    calendar_engine.sync_all_calendars()
    return get_calendar_tables(range_filter)

def push_calendar_digest_to_tg():
    digest_html = calendar_engine.build_telegram_calendar_digest()
    ok, msg = telegram_notifier.send_calendar_digest(digest_html)
    if ok:
        return f"✅ **Calendar & Outcomes Digest successfully sent to Calendar Telegram Channel (`{telegram_notifier.calendar_chat_id}`)!**"
    return f"⚠️ **Could not send Calendar Digest:** {msg} *(Configure Calendar Telegram Chat ID in Tab 3)*"

def handle_manual_event_save(
    evt_id: str,
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
    current_filter: str
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
        forward_now=forward_tg
    )
    cal_summary, cal_rows, _ = get_calendar_tables(current_filter)
    status_msg = f"✅ **Saved Event `{ev['id']}` ({ev['event']}) — Outcome: `{ev['actual']}`.**"
    if forward_tg:
        status_msg += " Dispatched update to Calendar Telegram Channel!"
    return status_msg, cal_summary, cal_rows

def save_admin_telegram_settings(
    news_token: str,
    news_chat: str,
    news_en: bool,
    cal_token: str,
    cal_chat: str,
    cal_en: bool,
    on_countdown: bool,
    on_outcome: bool,
    on_linked: bool
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
        alert_on_linked_news=on_linked
    )
    return (
        f"✅ **Admin Telegram Settings Saved!**\n"
        f"- **News Channel ID:** `{telegram_notifier.chat_id or 'Not Set'}` (Enabled: `{telegram_notifier.enabled}`)\n"
        f"- **Calendar & Outcomes Channel ID:** `{telegram_notifier.calendar_chat_id or 'Not Set'}` (Enabled: `{telegram_notifier.calendar_enabled}`)"
    )

def trigger_test_telegram(target_channel: str):
    ok, detail = telegram_notifier.send_test_alert(channel_type=target_channel)
    if ok:
        return f"✅ **Test alert delivered to {target_channel.upper()} Telegram channel!**"
    return f"❌ **Test alert failed for {target_channel.upper()} channel:** {detail}"

def get_sources_table():
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

def manual_refresh():
    news_worker.poll_cycle()
    time.sleep(1)
    return get_dashboard_tables()

def test_ai_rating(headline: str, summary: str):
    if not headline:
        return "Please enter a headline."
    res = ai_analyzer.analyze_news(headline, summary, "Manual Test")
    sent = res.get('sentiment', 'NEUTRAL')
    badge = "🟢 BULLISH" if sent == "BULLISH" else ("🔴 BEARISH" if sent == "BEARISH" else "⚪ NEUTRAL")
    return (
        f"**Impact Score:** {res.get('score', 0)}/10  |  **Sentiment:** {badge}  |  **Impact Level:** {res.get('impact', 'MEDIUM')}\n\n"
        f"**Affected Sectors/Stocks:** {', '.join(res.get('sectors', [])) or 'Broad Market'}\n\n"
        f"**Market Context:** {res.get('reasoning', '')}"
    )

def save_forwarding_rules(tg_selected: List[str], wa_selected: List[str], min_score: int):
    news_worker.save_config(tg_selected, wa_selected, min_score)
    updated_sources = get_sources_table()
    return f"✅ **Forwarding rules successfully updated!** ({len(tg_selected)} sources for Telegram, {len(wa_selected)} for WhatsApp, Min AI Score: {min_score})", updated_sources

all_source_names = [s["name"] for s in news_worker.sources]
default_tg_selected = [s["name"] for s in news_worker.sources if s.get("forward_telegram", True)]
default_wa_selected = [s["name"] for s in news_worker.sources if s.get("forward_whatsapp", True)]


# ─── Build Gradio Blocks UI ──────────────────────────────────────────────────

with gr.Blocks(title="EPM Pro News & Market Calendar Terminal", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 📰 EPM Pro Live Market News, Calendar & AI Sentiment Terminal")
    status_box = gr.Markdown(value="🟢 **Engine Status:** Online | Initializing...")

    with gr.Tabs():
        # ═══════════════════════════════════════════════════════════
        # TAB 1: Live Stream & AI Sentiment
        # ═══════════════════════════════════════════════════════════
        with gr.TabItem("📊 Live Market Feed & Sentiment Watch"):
            with gr.Row():
                refresh_btn = gr.Button("🔄 Force Refresh & Re-Score Feeds", variant="primary")

            gr.Markdown("### 🚨 High-Impact News & AI Sentiment Watch (Top Priority)")
            top_table = gr.Dataframe(
                headers=["Score", "Sentiment", "Impact", "Headline", "Sectors/Tickers", "AI Reasoning", "Source", "Relevance", "Time"],
                datatype=["str", "str", "str", "str", "str", "str", "str", "str", "str"],
                value=[],
                interactive=False,
                wrap=True
            )

            gr.Markdown("---")
            gr.Markdown("### 🌐 General & Broad Market News Wire (Secondary / Low Relevance)")
            bottom_table = gr.Dataframe(
                headers=["Time", "Source", "Headline", "Relevance", "Sentiment", "URL"],
                datatype=["str", "str", "str", "str", "str", "str"],
                value=[],
                interactive=False,
                wrap=True
            )

            gr.Markdown("---")
            gr.Markdown("### ⚡ Live AI Impact & Sentiment Tester")
            with gr.Row():
                test_title = gr.Textbox(label="Headline / Breaking News", placeholder="e.g. RBI unexpectedly cuts interest rates by 25 bps")
                test_desc = gr.Textbox(label="Summary (Optional)", placeholder="Context details...")
            
            analyze_btn = gr.Button("Analyze Headline with Gemini 2.5")
            ai_output = gr.Markdown()
            analyze_btn.click(test_ai_rating, inputs=[test_title, test_desc], outputs=ai_output)

        # ═══════════════════════════════════════════════════════════
        # TAB 2: Market Calendar, Live Timers, Outcomes & Linked News
        # ═══════════════════════════════════════════════════════════
        with gr.TabItem("📅 Market Calendar, Timers & Outcomes"):
            gr.Markdown("### ⏱️ Live Economic & Corporate Calendar (With Countdown Timers, Outcomes & Linked News)")
            cal_info_bar = gr.Markdown("Loading calendar & live timers...")

            with gr.Row():
                cal_filter = gr.Radio(
                    choices=[("All Scheduled Events", "all"), ("Today's Events", "today"), ("Next 7 Days", "week"), ("Upcoming Only", "upcoming")],
                    value="all",
                    label="Filter Calendar View",
                    scale=2
                )
                cal_sync_btn = gr.Button("🔄 Sync Calendar & Refresh Countdown Timers", variant="primary", scale=1)
                cal_push_tg_btn = gr.Button("📤 Push Calendar Digest to Telegram Channel", variant="secondary", scale=1)

            cal_action_msg = gr.Markdown()

            calendar_table = gr.Dataframe(
                headers=[
                    "Event ID",
                    "Date",
                    "Time (IST)",
                    "⏱ Live Timer",
                    "Asset / Symbol",
                    "Market Event",
                    "Impact",
                    "Previous",
                    "Forecast",
                    "🏁 Actual / Outcome",
                    "📊 Verdict",
                    "🔗 Linked Breaking News"
                ],
                datatype=["str", "str", "str", "str", "str", "str", "str", "str", "str", "str", "str", "str"],
                value=[],
                interactive=False,
                wrap=True
            )

            gr.Markdown("---")
            with gr.Accordion("✏️ Add Custom Calendar Event or Update Event Outcome Manually", open=False):
                gr.Markdown("Enter an existing **Event ID** from the table above to update its outcome, or leave Event ID blank to create a new scheduled event:")
                with gr.Row():
                    in_ev_id = gr.Textbox(label="Event ID (Optional for new)", placeholder="e.g. ind_cpi_2026-10-08")
                    in_ev_date = gr.Textbox(label="Date (YYYY-MM-DD)", value=now_ist().strftime("%Y-%m-%d"))
                    in_ev_time = gr.Textbox(label="Time IST (HH:MM)", value="14:00")
                    in_ev_sym = gr.Textbox(label="Symbol / Currency", value="🇮🇳 INR / NSE")
                    in_ev_imp = gr.Dropdown(choices=["HIGH", "MEDIUM", "LOW"], value="HIGH", label="Impact")
                with gr.Row():
                    in_ev_name = gr.Textbox(label="Event Title", placeholder="e.g. RBI Repo Rate Decision / Reliance Q2 Results", scale=2)
                    in_ev_prev = gr.Textbox(label="Previous", placeholder="e.g. 6.50%", scale=1)
                    in_ev_fore = gr.Textbox(label="Forecast", placeholder="e.g. 6.25%", scale=1)
                    in_ev_act = gr.Textbox(label="Actual Outcome", value="⏳ Pending", placeholder="e.g. 6.25% (25 bps Cut)", scale=1)
                    in_ev_sent = gr.Dropdown(
                        choices=["⏳ PENDING", "🟢 BULLISH", "🔴 BEARISH", "⚪ NEUTRAL"],
                        value="🟢 BULLISH",
                        label="Market Verdict",
                        scale=1
                    )
                with gr.Row():
                    in_ev_push = gr.Checkbox(value=True, label="Immediately forward this Event / Outcome to the Calendar Telegram Channel")
                    save_ev_btn = gr.Button("💾 Save Event / Outcome & Notify Channel", variant="primary")

            gr.Markdown("---")
            gr.Markdown("### 🏛️ 2026 Authoritative NSE/BSE & MCX Market Holidays")
            holidays_table = gr.Dataframe(
                headers=["Date", "Day", "Holiday Description", "NSE/BSE Equity & F&O", "MCX Commodities (Morning / Evening)"],
                datatype=["str", "str", "str", "str", "str"],
                value=[],
                interactive=False,
                wrap=True
            )

            cal_filter.change(get_calendar_tables, inputs=[cal_filter], outputs=[cal_info_bar, calendar_table, holidays_table])
            cal_sync_btn.click(sync_and_refresh_calendar, inputs=[cal_filter], outputs=[cal_info_bar, calendar_table, holidays_table])
            cal_push_tg_btn.click(push_calendar_digest_to_tg, outputs=[cal_action_msg])
            save_ev_btn.click(
                handle_manual_event_save,
                inputs=[in_ev_id, in_ev_date, in_ev_time, in_ev_sym, in_ev_name, in_ev_imp, in_ev_prev, in_ev_fore, in_ev_act, in_ev_sent, in_ev_push, cal_filter],
                outputs=[cal_action_msg, cal_info_bar, calendar_table]
            )

        # ═══════════════════════════════════════════════════════════
        # TAB 3: Admin Control Page — Telegram Channels & Sources
        # ═══════════════════════════════════════════════════════════
        with gr.TabItem("⚙️ Admin Control & Telegram Channel Settings"):
            gr.Markdown("### 🔐 Telegram Channels Configuration (Separate Channels for News vs. Market Calendar)")
            gr.Markdown(
                "Configure your **Live Breaking News** channel and your separate **Market Calendar & Outcomes** group/channel below. "
                "*(Tip: You can use the exact same Bot Token for both channels—just add the bot as an Admin to your second channel and enter its Chat ID!)*"
            )

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
                    with gr.Row():
                        adm_cal_countdown = gr.Checkbox(label="⏰ T-15m Countdown Alerts", value=telegram_notifier.alert_on_countdown)
                        adm_cal_outcome = gr.Checkbox(label="🏁 Actual Outcome Alerts", value=telegram_notifier.alert_on_outcome)
                        adm_cal_linked = gr.Checkbox(label="🔗 Linked News Alerts", value=telegram_notifier.alert_on_linked_news)
                    test_cal_tg_btn = gr.Button("🔔 Send Test Message to Calendar Channel")

            save_adm_tg_btn = gr.Button("💾 Save All Telegram Channel Settings", variant="primary")
            adm_tg_status = gr.Markdown()

            save_adm_tg_btn.click(
                save_admin_telegram_settings,
                inputs=[
                    adm_news_token, adm_news_chat, adm_news_enabled,
                    adm_cal_token, adm_cal_chat, adm_cal_enabled,
                    adm_cal_countdown, adm_cal_outcome, adm_cal_linked
                ],
                outputs=[adm_tg_status]
            )
            test_news_tg_btn.click(lambda: trigger_test_telegram("news"), outputs=[adm_tg_status])
            test_cal_tg_btn.click(lambda: trigger_test_telegram("calendar"), outputs=[adm_tg_status])

            gr.Markdown("---")
            gr.Markdown("### 📡 Connected News Sources & Selective Forwarding Rules")
            sources_table = gr.Dataframe(
                headers=["Source Name", "Category", "Ingestion Type", "Telegram Alerts", "WhatsApp Alerts", "Feed / Scrape URL"],
                datatype=["str", "str", "str", "str", "str", "str"],
                value=get_sources_table(),
                interactive=False,
                wrap=True
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

    refresh_btn.click(manual_refresh, outputs=[status_box, top_table, bottom_table])
    demo.load(get_dashboard_tables, outputs=[status_box, top_table, bottom_table])
    demo.load(get_calendar_tables, inputs=[cal_filter], outputs=[cal_info_bar, calendar_table, holidays_table])

# Mount Gradio UI inside FastAPI
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
