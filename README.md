---
title: EPM Pro Live News Engine
emoji: 📰
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 4.40.0
app_file: app.py
pinned: false
---

# 📰 EPM Pro Live News Engine (Standalone Microservice)

High-speed, decoupled real-time news scraping, deduplication, Gemini AI market impact scoring, and Telegram alert microservice.

---

## 🚀 Features

- **20+ Parallel Ingestion Feeds**:
  - **Indian Markets**: Moneycontrol (Markets & Corporate), Economic Times (Markets & Top Stories), Livemint (Markets & Companies), CNBC-TV18, Financial Express, NDTV Profit, Times of India Business, Zee Business, Inshorts Business API.
  - **Global & Macro**: Bloomberg, Reuters, Wall Street Journal (Markets & Business), MarketWatch (Top Stories & MarketPulse), The New York Times (Business & Economy), Yahoo Finance, CoinDesk.
- **SHA-256 Multi-Source Deduplication**: Eliminates duplicate stories across syndicated wires.
- **Gemini AI Market Impact Scoring**: Computes 1-10 impact rating, market bias (POSITIVE / NEGATIVE / NEUTRAL), affected sectors, and 1-sentence reasoning.
- **Direct Telegram Notifications**: Real-time push alerts on high-relevance or high-impact breaking news.
- **Dual Gradio Web UI + High-Speed REST API**: Access the visual web terminal in your browser or call `/api/news` from Trading Terminal.

---

## 📡 REST API Endpoints (For Trading Terminal)

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Web Visual News Terminal & Dashboard |
| `/health` | `GET` | Health check endpoint |
| `/api/news` | `GET` | Fetch latest news. Supports query params `limit`, `min_relevance`, `source`, `search` |
| `/api/sources` | `GET` | List all configured news sources |
| `/api/trigger` | `POST` | Force an immediate parallel scraping cycle |
| `/api/rate` | `POST` | On-demand Gemini AI impact score on any headline |

---

## 🛠️ Step-by-Step Deployment on Hugging Face Spaces (100% FREE)

### Step 1: Create a Space on Hugging Face
1. Go to [huggingface.co/spaces](https://huggingface.co/spaces) (sign up / log in).
2. Click **Create new Space**.
3. Set **Space name** (e.g. `epm-news-engine`).
4. Select **Gradio** as the Space SDK *(100% Free, no credit card required)*.
5. Under Space hardware, leave default (**CPU Basic · 2 vCPU · 16 GB · Free**).
6. Click **Create Space**.

### Step 2: Upload Files to Your Space
- **Option A: Web Browser Upload (Fastest)**:
  1. In your newly created Space, click the **Files** tab.
  2. Click **Add file** $\rightarrow$ **Upload files**.
  3. Upload the files from the `news_service/` folder:
     - `requirements.txt`
     - `app.py`
     - `news_worker.py`
     - `ai_analyzer.py`
     - `telegram_notifier.py`
     - `README.md`
  4. Click **Commit changes to main**.

- **Option B: Push via Git**:
  ```bash
  cd "news_service"
  git init
  git remote add origin https://huggingface.co/spaces/<YOUR_HF_USERNAME>/epm-news-engine
  git add .
  git commit -m "Deploy EPM Pro News Engine"
  git push -u origin main --force
  ```

### Step 3: Configure Secrets & Environment Variables
1. Go to your Space's **Settings** tab.
2. Scroll down to **Variables and secrets** $\rightarrow$ Click **New secret**.
3. Add the following secrets:
   - `GEMINI_API_KEY`: *(Your Google AI Studio Gemini API Key)*
   - `TELEGRAM_BOT_TOKEN`: *(Optional: Your Telegram Bot Token)*
   - `TELEGRAM_CHAT_ID`: *(Optional: Your Telegram Channel / Group Chat ID)*
   - `ENABLE_TELEGRAM_ALERTS`: `true`
   - `ENABLE_AI_SCORING`: `true`
4. The space will automatically install requirements and turn **Running**.

### Step 4: Access Your Endpoints
- **Visual Web UI**: `https://<YOUR_HF_USERNAME>-epm-news-engine.hf.space/`
- **Trading Terminal REST API**: `https://<YOUR_HF_USERNAME>-epm-news-engine.hf.space/api/news`
