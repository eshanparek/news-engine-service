# 📰 EPM Pro Multi-Market News & Calendar Engine (Standalone Microservice)

High-speed, decoupled real-time news scraping, multi-market economic & corporate calendar, live countdown timers, Gemini AI market impact scoring, and automated dual-channel Telegram alert microservice.

---

## 🌐 Live Cloud Deployment
- **Hosting Platform**: Northflank Developer Sandbox (Docker Container)
- **Live URL**: [https://p01--news-engine-service--dkhqtlpvx6bh.code.run/](https://p01--news-engine-service--dkhqtlpvx6bh.code.run/)
- **GitHub Repository**: [https://github.com/eshanparek/news-engine-service](https://github.com/eshanparek/news-engine-service)
- **Auto-Deploy**: Pushing to `main` branch automatically triggers a rebuild & live deployment on Northflank.

---

## 🚀 Key Systems & Architecture

### 1. Multi-Market Calendar Engine (`calendar_engine.py`)
- **5 Markets Supported**: `NSE`, `BSE`, `MCX`, `CRYPTO`, `NYSE`.
- **Live Countdown Timers**: Dynamic real-time calculation (`T-45m`, `T-15m`, `Live / In Progress`, `Completed`).
- **2026 Authoritative Trading Holidays**: Automated comparison matrix across Indian Exchanges (NSE, BSE, MCX morning/evening sessions), US Markets (NYSE EST/IST), and 24/7 Crypto.
- **Automated Morning IST Dispatches**:
  - `07:00 AM IST`: Auto-forwards Today's complete calendar snapshot as **5 separate market messages** + **Pre-Holiday Alert** (1 day before any trading holiday).
  - `07:05 AM IST`: Auto-forwards Tomorrow's scheduled events as **5 separate market messages**.
- **Real-Time Outcome Forwarding**: Automatically matches breaking news or manual inputs with scheduled events, calculating beats/misses and dispatching outcomes to Telegram.

### 2. High-Speed News Worker (`news_worker.py`)
- **20+ Parallel Feeds**: Scrapes Indian financial wires (Moneycontrol, ET, Livemint, CNBC-TV18, NDTV Profit, etc.) and global wires (Bloomberg, Reuters, WSJ, MarketWatch, CoinDesk).
- **SHA-256 Deduplication**: Drops duplicate stories across syndicated wires.
- **Adaptive Scraping & Bandwidth Protection**:
  - 3s during Indian market hours (09:00–15:45 IST)
  - 4s during US market hours (19:00–01:30 IST)
  - 8s off-peak daytime, 30s night, 45s weekends.
  - HTTP `304 Not Modified` / `ETag` conditional caching to prevent bandwidth waste.

### 3. Gemini AI Analysis (`ai_analyzer.py`)
- Evaluates headlines using Google Gemini 2.5 Flash.
- Produces: Impact Score (0–10), Sentiment (`BULLISH`, `BEARISH`, `NEUTRAL`), Impact Level (`HIGH`, `MEDIUM`, `LOW`), Affected Sectors & Tickers, and 1-sentence Market Reasoning.

### 4. Dual-Channel Telegram Dispatcher (`telegram_notifier.py`)
- **Channel 1 (Live Breaking News)**: High-impact breaking headlines and AI market analysis.
- **Channel 2 (Market Calendar & Outcomes)**: Pre-market snapshots, holiday notices, countdown alerts, and unfolding event results.
- **Flood Control & Anti-Spam**: Thread-safe minimum spacing (0.8s), backoff handling for Telegram HTTP 429 ("Too Many Requests").

### 5. Web UI & REST API (`app.py`)
- **Responsive 100% Full-Width UI**: Powered by Gradio Blocks with fixed-table layouts, zero horizontal sliders, and clean text wrapping.
- **FastAPI Endpoints**:
  - `GET /` — Visual Web Terminal (Live News, Calendar, Admin Settings).
  - `GET /api/news` — Latest news cache with filtering (`limit`, `min_relevance`, `source`, `search`).
  - `GET /api/calendar` — Active multi-market calendar events.
  - `GET /api/calendar/unified` — Unified holiday & corporate events feed for Trading Terminal integration.
  - `GET /api/calendar/ics` — iCal subscription feed for Apple/Google/Outlook calendars.
  - `POST /api/calendar/sync` — Force an immediate multi-market calendar scrape.
  - `POST /api/calendar/dispatch/today` — Trigger Today's 5-market snapshot.
  - `POST /api/calendar/dispatch/tomorrow` — Trigger Tomorrow's 5-market snapshot.
  - `POST /api/calendar/dispatch/holiday` — Trigger Pre-holiday trading notice.
  - `POST /api/calendar/event` — Create or update event outcome manually.

---

## 🛠️ Local Development & Running

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables** (Optional, can also configure in Tab 3 of Web UI):
   ```bash
   cp .env.example .env
   # Edit .env with your GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, etc.
   ```

3. **Start Microservice**:
   ```bash
   python app.py
   ```
   Open [http://localhost:7860](http://localhost:7860) in your browser.
