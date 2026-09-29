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

# 1. Start the Background Ingestion Worker
news_worker.start()

# 2. FastAPI Setup for Machine-to-Machine REST API
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
    limit: int = Query(30, ge=1, le=100),
    min_relevance: int = Query(0, ge=0, le=100),
    source: Optional[str] = None,
    search: Optional[str] = None
):
    """
    Returns latest cached news with optional filtering for Trading Terminal.
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
    """List of all configured parallel sources."""
    return {
        "total": len(news_worker.sources),
        "sources": news_worker.sources
    }

@app.post("/api/trigger")
def trigger_fetch(background_tasks: BackgroundTasks):
    """Force an immediate parallel fetch cycle."""
    background_tasks.add_task(news_worker.poll_cycle)
    return {"status": "triggered", "message": "News poll cycle triggered in background."}

@app.post("/api/rate")
def rate_headline(item: NewsItem):
    """On-demand Gemini AI impact score on any headline."""
    res = ai_analyzer.analyze_news(item.title, item.summary or item.title, item.source or "Custom")
    return res

# 3. Gradio Visual Dashboard for Free Hugging Face Spaces Web UI
def get_dashboard_data():
    items = list(news_worker.news_cache)
    rows = []
    for item in items[:25]:
        ai_score = f"{item.get('ai_score', '-')}/10" if "ai_score" in item else "Pending"
        impact = item.get("ai_impact", "-")
        rows.append([
            item.get("timestamp", ""),
            item.get("source", ""),
            item.get("title", ""),
            f"{item.get('relevance', 0)}%",
            f"{ai_score} ({impact})",
            item.get("link", "#")
        ])
    
    status_str = f"🟢 **Engine Status:** Online | **Cached News:** {len(news_worker.news_cache)} | **Active Sources:** {len(news_worker.sources)} | **Last Fetch:** {news_worker.last_fetch_time.strftime('%H:%M:%S') if news_worker.last_fetch_time else 'Init'}"
    return status_str, rows

def manual_trigger():
    news_worker.poll_cycle()
    return get_dashboard_data()

def test_ai_rating(headline: str, summary: str):
    if not headline:
        return "Please enter a headline."
    res = ai_analyzer.analyze_news(headline, summary, "Manual Test")
    return (
        f"**Impact Score:** {res.get('score', 0)}/10\n\n"
        f"**Direction:** {res.get('impact', 'NEUTRAL')}\n\n"
        f"**Sectors/Stocks:** {', '.join(res.get('sectors', [])) or 'General Market'}\n\n"
        f"**Reasoning:** {res.get('reasoning', '')}"
    )

with gr.Blocks(title="EPM Pro News Terminal", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 📰 EPM Pro Live Market News Microservice")
    gr.Markdown("Real-time parallel news scraper, Gemini AI market impact scoring, and high-frequency REST API.")
    
    status_box = gr.Markdown(value="🟢 **Engine Status:** Online | Initializing...")
    
    with gr.Row():
        refresh_btn = gr.Button("🔄 Force Refresh News", variant="primary")
    
    news_table = gr.Dataframe(
        headers=["Time", "Source", "Headline", "Relevance", "AI Impact", "URL"],
        datatype=["str", "str", "str", "str", "str", "str"],
        value=[],
        interactive=False,
        wrap=True
    )
    
    gr.Markdown("---")
    gr.Markdown("### 🤖 Test Gemini AI Impact Analyzer")
    with gr.Row():
        test_title = gr.Textbox(label="Headline / Breaking News", placeholder="e.g. RBI unexpectedly hikes repo rate by 25 bps")
        test_desc = gr.Textbox(label="Summary (Optional)", placeholder="Context details...")
    
    analyze_btn = gr.Button("Analyze Market Impact")
    ai_output = gr.Markdown()
    
    analyze_btn.click(test_ai_rating, inputs=[test_title, test_desc], outputs=ai_output)
    refresh_btn.click(manual_trigger, outputs=[status_box, news_table])
    demo.load(get_dashboard_data, outputs=[status_box, news_table])

# 4. Mount Gradio UI inside FastAPI App so both UI and REST API run on port 7860
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
