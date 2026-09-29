import os
import time
from typing import Optional, List, Dict
from datetime import datetime
from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import gradio as gr

load_dotenv()

from news_worker import news_worker
from ai_analyzer import ai_analyzer
from telegram_notifier import telegram_notifier
from whatsapp_notifier import whatsapp_notifier

# 1. Start Background Scraper & Scorer
news_worker.start()

# 2. FastAPI Machine-to-Machine Endpoints
app = FastAPI(
    title="EPM Pro Live News Engine",
    description="Decoupled high-speed real-time news scraping, AI impact evaluation, and Telegram/WhatsApp alerts service.",
    version="1.0.0"
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

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

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

# 3. Gradio Tabbed Interface
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

        # Top Priority Card (High Relevance or AI Impact)
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

    status_str = f"🟢 **Engine Status:** Online | **Total Cached Stories:** {len(items)} | **Priority Stories:** {len(top_rows)} | **Active Feeds:** {len(news_worker.sources)} | **Last Scrape:** {news_worker.last_fetch_time.strftime('%H:%M:%S') if news_worker.last_fetch_time else 'Init'}"
    return status_str, top_rows, bottom_rows

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

with gr.Blocks(title="EPM Pro News Terminal", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 📰 EPM Pro Live Market News Terminal")
    status_box = gr.Markdown(value="🟢 **Engine Status:** Online | Initializing...")

    with gr.Tabs():
        # TAB 1: Live Stream & AI Sentiment
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

        # TAB 2: News Channels & Forwarding Controls
        with gr.TabItem("📡 Connected News Channels & Forwarding Controls"):
            gr.Markdown("### 📋 All 22+ Connected News Sources")
            gr.Markdown("Below is the complete list of financial wires and market channels currently connected to your server:")
            
            sources_table = gr.Dataframe(
                headers=["Source Name", "Category", "Ingestion Type", "Telegram Alerts", "WhatsApp Alerts", "Feed / Scrape URL"],
                datatype=["str", "str", "str", "str", "str", "str"],
                value=get_sources_table(),
                interactive=False,
                wrap=True
            )

            gr.Markdown("---")
            gr.Markdown("### ⚙️ Selective Manual Forwarding Rules")
            gr.Markdown("Choose exactly which channels you want to forward to Telegram and WhatsApp, and set the minimum AI score filter:")

            min_score_slider = gr.Slider(minimum=0, maximum=10, value=news_worker.min_forward_score, step=1, label="Minimum AI Score Threshold (0 = Forward All News, 7 = High Impact Only)")

            with gr.Row():
                with gr.Column():
                    gr.Markdown("#### ✈️ Telegram Forwarding Channels")
                    tg_checkboxes = gr.CheckboxGroup(choices=all_source_names, value=default_tg_selected, label="Select Channels for Telegram Alerts")
                
                with gr.Column():
                    gr.Markdown("#### 💬 WhatsApp Forwarding Channels")
                    wa_checkboxes = gr.CheckboxGroup(choices=all_source_names, value=default_wa_selected, label="Select Channels for WhatsApp Alerts")

            save_rules_btn = gr.Button("💾 Save Channel Forwarding Rules", variant="primary")
            rules_status = gr.Markdown()

            save_rules_btn.click(
                save_forwarding_rules,
                inputs=[tg_checkboxes, wa_checkboxes, min_score_slider],
                outputs=[rules_status, sources_table]
            )

    refresh_btn.click(manual_refresh, outputs=[status_box, top_table, bottom_table])
    demo.load(get_dashboard_tables, outputs=[status_box, top_table, bottom_table])

# Mount Gradio UI inside FastAPI
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
