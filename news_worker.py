import os
import re
import time
import json
import sqlite3
import logging
import hashlib
import threading
import concurrent.futures
from datetime import datetime
from typing import List, Dict, Optional, Set
from urllib.parse import urlparse, urlunparse, urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from ai_analyzer import ai_analyzer
from telegram_notifier import telegram_notifier

logger = logging.getLogger("NewsWorker")

DB_PATH = os.getenv("ALERT_DB_PATH", "news_alerts.db")

def init_alert_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS sent_news (
                hash_id TEXT PRIMARY KEY,
                title TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error initializing alert database: {e}")

def is_hash_in_db(hash_id: str) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM sent_news WHERE hash_id = ?", (hash_id,))
        row = c.fetchone()
        conn.close()
        return bool(row)
    except Exception:
        return False

def record_hash_in_db(hash_id: str, title: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO sent_news (hash_id, title) VALUES (?, ?)", (hash_id, title[:200]))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"Error saving hash to DB: {e}")

# Initialize DB on load
init_alert_db()

def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation and source suffixes."""
    if not title:
        return ""
    t = title.lower()
    t = re.split(r'\s+[-|:]\s+[a-z0-9 .]+$', t)[0]
    t = re.sub(r'[^a-z0-9 ]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def canonical_link(link: str) -> str:
    """Standardize URL by stripping queries, anchors, trailing slashes."""
    if not link:
        return ""
    try:
        p = urlparse(link)
        scheme = (p.scheme or "https").lower()
        netloc = p.netloc.lower()
        path = p.path.rstrip("/")
        return urlunparse((scheme, netloc, path, "", "", ""))
    except Exception:
        return link.lower()

def compute_dedup_key(item: Dict) -> str:
    """Unique hash combining normalized title and link."""
    key = f"{normalize_title(item.get('title', ''))}|{canonical_link(item.get('link', ''))}"
    return hashlib.sha256(key.encode('utf-8')).hexdigest()

# Multi-Source Directory
DEFAULT_SOURCES = [
    # Indian Feeds
    {
        "id": "moneycontrol_markets",
        "name": "Moneycontrol Markets",
        "type": "rss",
        "url": "https://www.moneycontrol.com/rss/latestnews.xml",
        "fallback_scrape_url": "https://www.moneycontrol.com/news/business/markets/"
    },
    {
        "id": "moneycontrol_corp",
        "name": "Moneycontrol Corporate",
        "type": "rss",
        "url": "https://www.moneycontrol.com/rss/MC_corpuniversity.xml"
    },
    {
        "id": "et_markets",
        "name": "Economic Times Markets",
        "type": "rss",
        "url": "https://economictimes.indiatimes.com/markets/rssfeedstopstories.cms",
        "fallback_scrape_url": "https://economictimes.indiatimes.com/markets"
    },
    {
        "id": "et_top",
        "name": "Economic Times Top Stories",
        "type": "rss",
        "url": "https://economictimes.indiatimes.com/rssfeedstopstories.cms"
    },
    {
        "id": "livemint_markets",
        "name": "Livemint Markets",
        "type": "rss",
        "url": "https://www.livemint.com/rss/markets",
        "fallback_scrape_url": "https://www.livemint.com/market"
    },
    {
        "id": "livemint_companies",
        "name": "Livemint Companies",
        "type": "rss",
        "url": "https://www.livemint.com/rss/companies"
    },
    {
        "id": "cnbc_tv18",
        "name": "CNBC TV18",
        "type": "rss",
        "url": "https://www.cnbctv18.com/commonrss/allnews.xml",
        "fallback_scrape_url": "https://www.cnbctv18.com/market/"
    },
    {
        "id": "financial_express",
        "name": "Financial Express",
        "type": "rss",
        "url": "https://www.financialexpress.com/market/feed/"
    },
    {
        "id": "ndtv_profit",
        "name": "NDTV Profit",
        "type": "rss",
        "url": "https://feeds.feedburner.com/ndtvprofit-latest"
    },
    {
        "id": "times_of_india",
        "name": "Times of India Business",
        "type": "rss",
        "url": "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms"
    },
    {
        "id": "zee_business",
        "name": "Zee Business",
        "type": "rss",
        "url": "https://www.zeebiz.com/markets/rss.xml"
    },
    {
        "id": "inshorts_business",
        "name": "Inshorts Business",
        "type": "inshorts",
        "category": "business"
    },

    # Global Feeds
    {
        "id": "bloomberg_markets",
        "name": "Bloomberg Markets",
        "type": "rss",
        "url": "https://www.bloomberg.com/feeds/bpol/markets.xml",
        "fallback_scrape_url": "https://www.bloomberg.com/markets"
    },
    {
        "id": "reuters_markets",
        "name": "Reuters Markets",
        "type": "rss",
        "url": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
        "fallback_scrape_url": "https://www.reuters.com/markets/"
    },
    {
        "id": "wsj_markets",
        "name": "Wall Street Journal",
        "type": "rss",
        "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"
    },
    {
        "id": "wsj_business",
        "name": "WSJ Business",
        "type": "rss",
        "url": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml"
    },
    {
        "id": "marketwatch_top",
        "name": "MarketWatch Top Stories",
        "type": "rss",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"
    },
    {
        "id": "marketwatch_pulse",
        "name": "MarketWatch MarketPulse",
        "type": "rss",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"
    },
    {
        "id": "nyt_business",
        "name": "New York Times Business",
        "type": "rss",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"
    },
    {
        "id": "nyt_economy",
        "name": "New York Times Economy",
        "type": "rss",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml"
    },
    {
        "id": "yahoo_finance",
        "name": "Yahoo Finance",
        "type": "rss",
        "url": "https://finance.yahoo.com/news/rssindex"
    },
    {
        "id": "coindesk_crypto",
        "name": "CoinDesk Crypto & Macro",
        "type": "rss",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "fallback_scrape_url": "https://www.coindesk.com/"
    }
]

CORE_KEYWORDS = [
    "NIFTY", "SENSEX", "BANKNIFTY", "RBI", "FED", "RATE HIKE", "RATE CUT",
    "INFLATION", "CPI", "GDP", "CRUDE", "BRENT", "OPEC", "EARNINGS", "QUARTER",
    "Q1", "Q2", "Q3", "Q4", "PROFIT", "REVENUE", "ACQUISITION", "MERGER",
    "IPO", "DIVIDEND", "BONUS", "BUYBACK", "SEBI", "US TREASURY", "YIELD",
    "RELIANCE", "TCS", "HDFC", "INFOSYS", "ICICI", "TATA", "ADANI", "SBI", "L&T"
]

class NewsEngineWorker:
    def __init__(self):
        self.sources = DEFAULT_SOURCES
        self.news_cache: List[Dict] = []
        self.seen_hashes: Set[str] = set()
        self.alerted_hashes: Set[str] = set()
        self.is_running = False
        self.is_initialized = False # Cold-start warmup flag
        self.last_fetch_time: Optional[datetime] = None
        self.refresh_interval = int(os.getenv("REFRESH_INTERVAL", "1")) # 1-second ultra-high frequency cycle
        self.enable_ai = os.getenv("ENABLE_AI_SCORING", "true").lower() == "true"
        self.lock = threading.Lock()
        
        # High-performance connection-pooled session
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=35, pool_maxsize=35, max_retries=Retry(total=1, backoff_factor=0.1))
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        })
        self._load_saved_hashes()

    def _load_saved_hashes(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT hash_id FROM sent_news")
            for row in c.fetchall():
                self.alerted_hashes.add(row[0])
                self.seen_hashes.add(row[0])
            conn.close()
            logger.info(f"Loaded {len(self.alerted_hashes)} existing alert hashes from DB.")
        except Exception as e:
            logger.debug(f"Could not load hashes: {e}")

    def clean_text(self, html_or_text: str) -> str:
        if not html_or_text:
            return ""
        if "<" in html_or_text and ">" in html_or_text:
            try:
                soup = BeautifulSoup(html_or_text, "html.parser")
                text = soup.get_text()
            except Exception:
                text = html_or_text
        else:
            text = html_or_text
        text = " ".join(text.split())
        return text[:280] + ("..." if len(text) > 280 else "")

    def calculate_relevance(self, text: str) -> int:
        score = 20
        text_upper = text.upper()
        
        matches = sum(1 for kw in CORE_KEYWORDS if kw in text_upper)
        score += min(matches * 15, 75)
        
        if any(urgent in text_upper for urgent in ["BREAKING", "ALERT", "SURGES", "CRASHES", "EMERGENCY", "SANCTION", "WAR", "TARIFF"]):
            score += 15

        return min(score, 100)

    def fetch_inshorts(self, category: str = "business") -> List[Dict]:
        items = []
        try:
            url = f"https://inshorts.com/en/read/{category}"
            resp = self.session.get(url, timeout=2.5)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("div", class_=re.compile(r"news-card"))
                for c in cards:
                    headline_tag = c.find(attrs={"itemprop": "headline"}) or c.find("span", class_="headline")
                    body_tag = c.find(attrs={"itemprop": "articleBody"}) or c.find("div", class_="articleBody")
                    source_link_tag = c.find("a", class_="source")
                    
                    title = headline_tag.text.strip() if headline_tag else ""
                    body = body_tag.text.strip() if body_tag else ""
                    link = source_link_tag.get("href") if source_link_tag else url
                    
                    if title:
                        items.append({
                            "title": title,
                            "summary": self.clean_text(body or title),
                            "source": "Inshorts",
                            "link": link,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "relevance": self.calculate_relevance(title + " " + body)
                        })
        except Exception as e:
            logger.debug(f"Inshorts fetch failed: {e}")
        return items

    def fetch_single_feed(self, source: Dict) -> List[Dict]:
        import warnings
        from bs4 import XMLParsedAsHTMLWarning
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

        results = []
        try:
            if source.get("type") == "inshorts":
                return self.fetch_inshorts(source.get("category", "business"))

            url = source.get("url")
            if not url:
                return results

            resp = self.session.get(url, timeout=2.5)
            if resp.status_code == 200:
                soup = None
                try:
                    soup = BeautifulSoup(resp.content, "xml")
                except Exception:
                    soup = BeautifulSoup(resp.content, "html.parser")

                if soup:
                    rss_items = soup.find_all("item")
                    if not rss_items:
                        rss_items = soup.find_all("entry")

                    for it in rss_items[:12]:
                        title = it.find("title").text if it.find("title") else ""
                        link_tag = it.find("link")
                        link = ""
                        if link_tag:
                            link = link_tag.get("href") if link_tag.has_attr("href") else link_tag.text
                        
                        desc_tag = it.find("description") or it.find("summary") or it.find("content")
                        desc = desc_tag.text if desc_tag else ""
                        pub_tag = it.find("pubDate") or it.find("published") or it.find("updated")
                        pub_date = pub_tag.text if pub_tag else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        if title and len(title.strip()) > 10:
                            results.append({
                                "title": title.strip(),
                                "summary": self.clean_text(desc or title),
                                "source": source["name"],
                                "link": link.strip(),
                                "timestamp": str(pub_date).strip(),
                                "relevance": self.calculate_relevance(title + " " + desc)
                            })

            if not results and source.get("fallback_scrape_url"):
                scrape_url = source["fallback_scrape_url"]
                s_resp = self.session.get(scrape_url, timeout=2.5)
                if s_resp.status_code == 200:
                    s_soup = BeautifulSoup(s_resp.content, "html.parser")
                    anchors = s_soup.find_all("a", href=True)
                    for a in anchors:
                        text = a.get_text().strip()
                        href = a["href"]
                        if len(text) > 35 and not href.startswith("#") and not href.startswith("javascript:"):
                            full_link = urljoin(scrape_url, href)
                            results.append({
                                "title": text,
                                "summary": text,
                                "source": source["name"],
                                "link": full_link,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "relevance": self.calculate_relevance(text)
                            })
                            if len(results) >= 8:
                                break
        except Exception as e:
            logger.debug(f"Feed error ({source.get('name')}): {e}")

        return results

    def process_and_dispatch_single_item(self, item: Dict):
        """Immediately rate and forward a single newly detected story in real time."""
        hid = item.get("id") or compute_dedup_key(item)
        with self.lock:
            if hid in self.alerted_hashes or is_hash_in_db(hid):
                return
            self.alerted_hashes.add(hid)
            record_hash_in_db(hid, item.get("title", ""))

        # 1. AI Impact & Sentiment Rating (Immediate)
        rating = ai_analyzer.analyze_news(item["title"], item.get("summary", "") or item["title"], item.get("source", ""))
        item["ai_score"] = rating.get("score", 5)
        item["ai_sentiment"] = rating.get("sentiment", "NEUTRAL")
        item["ai_impact"] = rating.get("impact", "MEDIUM")
        item["ai_sectors"] = rating.get("sectors", [])
        item["ai_reasoning"] = rating.get("reasoning", "")

        # 2. Instant Real-Time Dispatch to Telegram
        telegram_notifier.send_news_alert(item)

    def fetch_all_sources(self) -> List[Dict]:
        all_news = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
            futures = [executor.submit(self.fetch_single_feed, src) for src in self.sources]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    res = fut.result()
                    if res:
                        all_news.extend(res)
                except Exception:
                    pass

        newly_arrived = []
        for item in all_news:
            h = compute_dedup_key(item)
            if h not in self.seen_hashes:
                self.seen_hashes.add(h)
                item["id"] = h
                newly_arrived.append(item)

        if len(self.seen_hashes) > 3000:
            self.seen_hashes = set(list(self.seen_hashes)[-1500:])

        return newly_arrived, all_news

    def poll_cycle(self):
        """Ultra-fast 1-second poll cycle: checks all feeds in parallel with pooled HTTP connections."""
        newly_arrived, all_scraped = self.fetch_all_sources()

        # Update Live Cache for Dashboard
        if all_scraped:
            combined = newly_arrived + self.news_cache
            combined.sort(key=lambda x: x.get("relevance", 0), reverse=True)
            self.news_cache = combined[:80]

        # First boot: record existing backlog so we don't spam historical news
        if not self.is_initialized:
            for it in all_scraped:
                hid = it.get("id") or compute_dedup_key(it)
                self.alerted_hashes.add(hid)
                record_hash_in_db(hid, it.get("title", ""))
            self.is_initialized = True
            logger.info(f"Cold-start warmup complete. {len(all_scraped)} backlog items cached without alerting.")
            # Rate a few items for visual dashboard
            for it in self.news_cache[:15]:
                if "ai_score" not in it:
                    r = ai_analyzer.analyze_news(it["title"], it.get("summary", "") or it["title"], it.get("source", ""))
                    it["ai_score"] = r.get("score", 5)
                    it["ai_sentiment"] = r.get("sentiment", "NEUTRAL")
                    it["ai_impact"] = r.get("impact", "MEDIUM")
                    it["ai_sectors"] = r.get("sectors", [])
                    it["ai_reasoning"] = r.get("reasoning", "")
        else:
            # LIVE RUN: Every single freshly arrived story is scored and sent IMMEDIATELY as it arrives
            if newly_arrived:
                for item in newly_arrived:
                    threading.Thread(target=self.process_and_dispatch_single_item, args=(item,), daemon=True).start()

        self.last_fetch_time = datetime.now()

    def run_worker_loop(self):
        self.is_running = True
        logger.info("News Engine 1-second ultra-high frequency loop started.")
        while self.is_running:
            try:
                self.poll_cycle()
                time.sleep(self.refresh_interval)
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(1)

    def start(self):
        if not self.is_running:
            t = threading.Thread(target=self.run_worker_loop, daemon=True)
            t.start()

# Global worker instance
news_worker = NewsEngineWorker()
