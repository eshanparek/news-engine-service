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

# 1. Start Background Scraper & Scorer
news_worker.start()

# 2. FastAPI Machine-to-Machine Endpoints
app = FastAPI(
    title="EPM Pro Live News Engine",
    description="Decoupled high-speed real-time news scraping, AI impact evaluation, and Telegram alerts service.",
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
    """
    Returns latest news with AI sentiment & impact scores.
    """
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

# 3. Stacked Top/Bottom Dashboard
def get_dashboard_tables():
    items = list(news_worker.news_cache)
    
    top_rows = []
    bottom_rows = []

    for it in items:
        score = it.get("ai_score", 5)
        sentiment = it.get("ai_sentiment", "NEUTRAL")
        impact = it.get("ai_impact", "MEDIUM")
        relevance = it.get("relevance", 0)
        
        # Sentiment format
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

        # High Impact & Priority Market News (Top Card)
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
            # General / Lower Relevance News (Bottom Card)
            bottom_rows.append([
                time_str,
                source,
                title,
                f"{relevance}%",
                sent_badge,
                link
            ])

    if not top_rows:
        top_rows.append(["-", "⚪ Evaluating...", "-", "Analyzing high priority news items with Gemini 2.5...", "-", "Please wait a moment...", "-", "-", "-"])

    if not bottom_rows:
        bottom_rows.append(["-", "-", "No general news items in cache", "-", "-", "-"])

    status_str = f"🟢 **Engine Status:** Online | **Total Cached Stories:** {len(items)} | **Priority Stories:** {len(top_rows)} | **General Stories:** {len(bottom_rows)} | **Active Feeds:** {len(news_worker.sources)} | **Last Scrape:** {news_worker.last_fetch_time.strftime('%H:%M:%S') if news_worker.last_fetch_time else 'Init'}"
    return status_str, top_rows, bottom_rows

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

with gr.Blocks(title="EPM Pro News Terminal", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 📰 EPM Pro Live Market News & AI Sentiment Terminal")
    gr.Markdown("Real-time parallel multi-feed news scraper, Gemini 2.5 AI sentiment & volatility scoring, and automated Telegram alert engine.")
    
    status_box = gr.Markdown(value="🟢 **Engine Status:** Online | Initializing...")
    
    with gr.Row():
        refresh_btn = gr.Button("🔄 Force Refresh & Re-Score Feeds", variant="primary")

    # TOP CARD: High Impact & Priority News
    gr.Markdown("---")
    gr.Markdown("### 🚨 High-Impact News & AI Sentiment Watch (Top Priority)")
    top_table = gr.Dataframe(
        headers=["Score", "Sentiment", "Impact", "Headline", "Sectors/Tickers", "AI Reasoning", "Source", "Relevance", "Time"],
        datatype=["str", "str", "str", "str", "str", "str", "str", "str", "str"],
        value=[],
        interactive=False,
        wrap=True
    )

    # BOTTOM CARD: General & Low Relevance News
    gr.Markdown("---")
    gr.Markdown("### 🌐 General & Broad Market News Wire (Secondary / Low Relevance)")
    bottom_table = gr.Dataframe(
        headers=["Time", "Source", "Headline", "Relevance", "Sentiment", "URL"],
        datatype=["str", "str", "str", "str", "str", "str"],
        value=[],
        interactive=False,
        wrap=True
    )

    # TESTER SECTION
    gr.Markdown("---")
    gr.Markdown("### ⚡ Live AI Impact & Sentiment Tester")
    with gr.Row():
        test_title = gr.Textbox(label="Headline / Breaking News", placeholder="e.g. RBI unexpectedly cuts interest rates by 25 bps")
        test_desc = gr.Textbox(label="Summary (Optional)", placeholder="Context details...")
    
    analyze_btn = gr.Button("Analyze Headline with Gemini 2.5")
    ai_output = gr.Markdown()
    
    analyze_btn.click(test_ai_rating, inputs=[test_title, test_desc], outputs=ai_output)
    refresh_btn.click(manual_refresh, outputs=[status_box, top_table, bottom_table])
    demo.load(get_dashboard_tables, outputs=[status_box, top_table, bottom_table])

# Mount Gradio UI inside FastAPI
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
