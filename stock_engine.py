#!/usr/bin/env python3
"""
Stock News, Corporate Disclosures & Multi-Asset Taxonomy Engine
Institutional Intelligence Engine for NSE, BSE, MCX, NYSE, and NASDAQ.
Categorizes Equities into NSE Broad Market & Sectoral Indices, US Benchmarks, and MCX Commodities.
"""

import os
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("StockEngine")

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")
TAXONOMY_FILE = os.path.join(CONFIG_DIR, "stock_taxonomy.json")
STOCK_DB_FILE = os.path.join(os.path.dirname(__file__), "stock_news.db")

DEFAULT_NSE_TAXONOMY = {
    "broad_indices": [
        {"id": "NIFTY50", "name": "Nifty 50", "exchange": "NSE", "description": "Top 50 large-cap blue-chips"},
        {"id": "NIFTY100", "name": "Nifty 100", "exchange": "NSE", "description": "Top 100 companies representing 76% market cap"},
        {"id": "NIFTY200", "name": "Nifty 200", "exchange": "NSE", "description": "Top 200 companies (Large and Mid cap)"},
        {"id": "NIFTY500", "name": "Nifty 500", "exchange": "NSE", "description": "Top 500 companies representing 96% market cap"},
        {"id": "NIFTYMID100", "name": "Nifty Midcap 100", "exchange": "NSE", "description": "Key 100 mid-cap growth enterprises"},
        {"id": "NIFTYSM100", "name": "Nifty Smallcap 100", "exchange": "NSE", "description": "High-growth small-cap enterprises"},
        {"id": "SENSEX", "name": "BSE Sensex 30", "exchange": "BSE", "description": "Benchmark 30 established blue-chips"}
    ],
    "sectoral_indices": [
        {"id": "BANKNIFTY", "name": "Bank Nifty", "exchange": "NSE", "sector": "Banking & Financials"},
        {"id": "NIFTYFIN", "name": "Nifty Financial Services", "exchange": "NSE", "sector": "Banking & Financials"},
        {"id": "NIFTYIT", "name": "Nifty IT", "exchange": "NSE", "sector": "IT & Technology"},
        {"id": "NIFTYAUTO", "name": "Nifty Auto", "exchange": "NSE", "sector": "Automobiles & Mobility"},
        {"id": "NIFTYPHARMA", "name": "Nifty Pharma", "exchange": "NSE", "sector": "Pharma & Healthcare"},
        {"id": "NIFTYFMCG", "name": "Nifty FMCG", "exchange": "NSE", "sector": "FMCG & Consumer Goods"},
        {"id": "NIFTYMETAL", "name": "Nifty Metal", "exchange": "NSE", "sector": "Metals & Mining"},
        {"id": "NIFTYENERGY", "name": "Nifty Energy", "exchange": "NSE", "sector": "Energy, Oil & Gas"},
        {"id": "NIFTYOILGAS", "name": "Nifty Oil & Gas", "exchange": "NSE", "sector": "Energy, Oil & Gas"},
        {"id": "NIFTYREALTY", "name": "Nifty Realty", "exchange": "NSE", "sector": "Real Estate & Infra"},
        {"id": "NIFTYMEDIA", "name": "Nifty Media", "exchange": "NSE", "sector": "Media & Entertainment"},
        {"id": "NIFTYHEALTH", "name": "Nifty Healthcare", "exchange": "NSE", "sector": "Pharma & Healthcare"}
    ],
    "us_indices": [
        {"id": "DJIA", "name": "Dow Jones Industrial Average (DJIA)", "exchange": "NYSE", "description": "30 Prominent US Blue-chips"},
        {"id": "NDX", "name": "Nasdaq 100", "exchange": "NASDAQ", "description": "Top 100 Global Tech & Non-financial Giants"},
        {"id": "SPX", "name": "S&P 500", "exchange": "US", "description": "500 Leading US Large-Cap Enterprises"}
    ],
    "mcx_commodities": [
        {"id": "GOLD", "name": "MCX Gold (1kg / Mini)", "category": "Bullion", "symbol": "GOLD"},
        {"id": "SILVER", "name": "MCX Silver (30kg / Mini)", "category": "Bullion", "symbol": "SILVER"},
        {"id": "CRUDEOIL", "name": "MCX Crude Oil", "category": "Energy", "symbol": "CRUDEOIL"},
        {"id": "NATGAS", "name": "MCX Natural Gas", "category": "Energy", "symbol": "NATURALGAS"},
        {"id": "COPPER", "name": "MCX Copper", "category": "Base Metals", "symbol": "COPPER"},
        {"id": "ALUMINIUM", "name": "MCX Aluminium", "category": "Base Metals", "symbol": "ALUMINIUM"},
        {"id": "ZINC", "name": "MCX Zinc", "category": "Base Metals", "symbol": "ZINC"},
        {"id": "LEAD", "name": "MCX Lead", "category": "Base Metals", "symbol": "LEAD"},
        {"id": "NICKEL", "name": "MCX Nickel", "category": "Base Metals", "symbol": "NICKEL"},
        {"id": "MCXBULLDEX", "name": "MCX Bulldex Index", "category": "Indices", "symbol": "MCXBULLDEX"},
        {"id": "MCXMETALDEX", "name": "MCX Metaldex Index", "category": "Indices", "symbol": "MCXMETALDEX"},
        {"id": "MCXENERGY", "name": "MCX Energy Index", "category": "Indices", "symbol": "MCXENERGY"}
    ]
}

SEED_STOCK_NEWS = [
    {
        "id": "stk_001",
        "ticker": "RELIANCE",
        "company": "Reliance Industries Limited",
        "exchange": "NSE",
        "market": "NSE",
        "index_tags": ["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYENERGY", "SENSEX"],
        "sector": "Energy, Oil & Gas",
        "title": "Reliance AGM: ₹75,000 Cr New Clean Energy Gigafactory Roadmap Unveiled",
        "summary": "Reliance Industries announces timeline for commissioning its 20GW solar module and energy storage battery manufacturing gigafactories at Jamnagar.",
        "sentiment": "BULLISH",
        "impact": "HIGH",
        "disclosure_type": "CORPORATE_ACTION",
        "timestamp": "2026-11-04 22:45:00",
        "filing_url": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        "source": "NSE Corporate Filings"
    },
    {
        "id": "stk_002",
        "ticker": "HDFCBANK",
        "company": "HDFC Bank Limited",
        "exchange": "NSE",
        "market": "NSE",
        "index_tags": ["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "BANKNIFTY", "NIFTYFIN", "SENSEX"],
        "sector": "Banking & Financials",
        "title": "HDFC Bank Q2 Net Profit Jumps 18.2% YoY to ₹18,420 Cr, Asset Quality Robust",
        "summary": "India's largest private lender reports net interest income growth of 16.5% with Gross NPA moderating to 1.18% vs 1.24% QoQ.",
        "sentiment": "BULLISH",
        "impact": "HIGH",
        "disclosure_type": "EARNINGS",
        "timestamp": "2026-11-04 22:15:00",
        "filing_url": "https://www.bseindia.com/corporates/ann.html",
        "source": "BSE Disclosures"
    },
    {
        "id": "stk_003",
        "ticker": "TCS",
        "company": "Tata Consultancy Services",
        "exchange": "NSE",
        "market": "NSE",
        "index_tags": ["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYIT", "SENSEX"],
        "sector": "IT & Technology",
        "title": "TCS Bags $1.2 Billion Multi-Year Cloud & AI Modernization Deal with European Banking Conglomerate",
        "summary": "TCS to deploy proprietary Cognix platform and generative AI microservices across 14 European markets.",
        "sentiment": "BULLISH",
        "impact": "HIGH",
        "disclosure_type": "CONTRACT_WIN",
        "timestamp": "2026-11-04 21:50:00",
        "filing_url": "https://www.nseindia.com",
        "source": "NSE Corporate Announcements"
    },
    {
        "id": "stk_004",
        "ticker": "CRUDEOIL",
        "company": "MCX Crude Oil",
        "exchange": "MCX",
        "market": "MCX",
        "index_tags": ["MCXENERGY"],
        "sector": "Energy, Oil & Gas",
        "title": "OPEC+ Extends Voluntary Supply Restraints of 2.2M BPD into Q1 2027; MCX Crude Contracts Rally 2.4%",
        "summary": "Crude oil futures surged as energy ministers confirmed strict quota compliance and extended output discipline to stabilize global reserves.",
        "sentiment": "BULLISH",
        "impact": "HIGH",
        "disclosure_type": "COMMODITY_CATALYST",
        "timestamp": "2026-11-04 21:30:00",
        "filing_url": "https://www.mcxindia.com",
        "source": "MCX Commodity Wire"
    },
    {
        "id": "stk_005",
        "ticker": "NVDA",
        "company": "NVIDIA Corporation",
        "exchange": "NASDAQ",
        "market": "NASDAQ",
        "index_tags": ["NDX", "SPX"],
        "sector": "IT & Technology",
        "title": "NVIDIA Form 8-K: Blackwell Ultra GPU Architecture Exceeds Delivery Targets; SEC Edgar Filing",
        "summary": "Nvidia files Form 8-K detailing cloud enterprise orders exceeding $22B for next-generation AI infrastructure clusters.",
        "sentiment": "BULLISH",
        "impact": "HIGH",
        "disclosure_type": "SEC_EDGAR_FILING",
        "timestamp": "2026-11-04 20:45:00",
        "filing_url": "https://www.sec.gov/edgar",
        "source": "SEC EDGAR"
    },
    {
        "id": "stk_006",
        "ticker": "GOLD",
        "company": "MCX Gold Futures",
        "exchange": "MCX",
        "market": "MCX",
        "index_tags": ["MCXBULLDEX"],
        "sector": "Commodities",
        "title": "Central Bank Sovereign Bullion Reserves Accumulation Hits Record 1,200 Tonnes; Gold Tests Fresh Highs",
        "summary": "Sovereign reserve rebalancing drives institutional physical delivery demand on MCX bullion delivery vaults.",
        "sentiment": "BULLISH",
        "impact": "MEDIUM",
        "disclosure_type": "COMMODITY_CATALYST",
        "timestamp": "2026-11-04 20:00:00",
        "filing_url": "https://www.mcxindia.com",
        "source": "MCX Market Intelligence"
    },
    {
        "id": "stk_007",
        "ticker": "TATAMOTORS",
        "company": "Tata Motors Passenger Vehicles Limited",
        "exchange": "NSE",
        "market": "NSE",
        "index_tags": ["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYAUTO"],
        "sector": "Automobiles & Mobility",
        "title": "Tata Motors Demerger Milestone: JLR and Commercial Vehicles Separate Scrip Listings Finalized",
        "summary": "Company submits scheme of arrangement clearance letter to NSE and BSE; shareholder record dates slated for early December.",
        "sentiment": "BULLISH",
        "impact": "HIGH",
        "disclosure_type": "CORPORATE_ACTION",
        "timestamp": "2026-11-04 19:30:00",
        "filing_url": "https://www.bseindia.com",
        "source": "BSE Announcements"
    },
    {
        "id": "stk_008",
        "ticker": "AAPL",
        "company": "Apple Inc.",
        "exchange": "NASDAQ",
        "market": "NASDAQ",
        "index_tags": ["DJIA", "NDX", "SPX"],
        "sector": "IT & Technology",
        "title": "Apple Form 10-K Annual Filing: Services Revenue Accelerates to $96B, Share Repurchase Executed",
        "summary": "Apple files definitive Form 10-K showing accelerated active device install base topping 2.3 billion globally.",
        "sentiment": "NEUTRAL",
        "impact": "MEDIUM",
        "disclosure_type": "SEC_EDGAR_FILING",
        "timestamp": "2026-11-04 18:40:00",
        "filing_url": "https://www.sec.gov/edgar",
        "source": "SEC EDGAR"
    }
]

class StockNewsEngine:
    def __init__(self, db_path: str = STOCK_DB_FILE):
        self.db_path = db_path
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.taxonomy = self._load_taxonomy()
        self._init_db()

    def _load_taxonomy(self) -> Dict:
        if os.path.exists(TAXONOMY_FILE):
            try:
                with open(TAXONOMY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading stock taxonomy: {e}")
        # Save default
        with open(TAXONOMY_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_NSE_TAXONOMY, f, indent=2)
        return DEFAULT_NSE_TAXONOMY

    def save_taxonomy(self, new_tax: Dict):
        self.taxonomy = new_tax
        tmp = TAXONOMY_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new_tax, f, indent=2)
        os.replace(tmp, TAXONOMY_FILE)

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_disclosures (
                id TEXT PRIMARY KEY,
                ticker TEXT,
                company TEXT,
                exchange TEXT,
                market TEXT,
                index_tags TEXT,
                sector TEXT,
                title TEXT,
                summary TEXT,
                sentiment TEXT,
                impact TEXT,
                disclosure_type TEXT,
                timestamp TEXT,
                filing_url TEXT,
                source TEXT
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_market ON stock_disclosures(market)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_sector ON stock_disclosures(sector)")
            conn.commit()

            # Seed if empty
            cursor.execute("SELECT count(*) FROM stock_disclosures")
            if cursor.fetchone()[0] == 0:
                for s in SEED_STOCK_NEWS:
                    cursor.execute("""
                    INSERT INTO stock_disclosures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        s["id"], s["ticker"], s["company"], s["exchange"], s["market"],
                        json.dumps(s["index_tags"]), s["sector"], s["title"], s["summary"],
                        s["sentiment"], s["impact"], s["disclosure_type"], s["timestamp"],
                        s["filing_url"], s["source"]
                    ))
                conn.commit()

    def fetch_stock_news(self, market: str = "ALL", index_tag: str = "ALL", sector: str = "ALL", search: str = "") -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM stock_disclosures WHERE 1=1"
            params = []
            if market and market.upper() != "ALL":
                query += " AND UPPER(market) = ?"
                params.append(market.upper())
            if sector and sector.upper() != "ALL":
                query += " AND UPPER(sector) = ?"
                params.append(sector.upper())
            if search:
                query += " AND (UPPER(ticker) LIKE ? OR UPPER(company) LIKE ? OR UPPER(title) LIKE ?)"
                kw = f"%{search.upper()}%"
                params.extend([kw, kw, kw])
            
            query += " ORDER BY timestamp DESC LIMIT 60"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for r in rows:
                tags = []
                try:
                    tags = json.loads(r[5])
                except Exception:
                    tags = []
                
                # Filter by index_tag if specified
                if index_tag and index_tag.upper() != "ALL":
                    if index_tag.upper() not in [t.upper() for t in tags]:
                        continue
                
                results.append({
                    "id": r[0],
                    "ticker": r[1],
                    "company": r[2],
                    "exchange": r[3],
                    "market": r[4],
                    "index_tags": tags,
                    "sector": r[6],
                    "title": r[7],
                    "summary": r[8],
                    "sentiment": r[9],
                    "impact": r[10],
                    "disclosure_type": r[11],
                    "timestamp": r[12],
                    "filing_url": r[13],
                    "source": r[14]
                })
            return results


    def fetch_stock_history(self, ticker: str, limit: int = 5) -> List[Dict]:
        """Fetch chronological history (last 4-5 events) for a specific ticker."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM stock_disclosures 
            WHERE UPPER(ticker) = ? 
            ORDER BY timestamp DESC LIMIT ?
            """, (ticker.upper().strip(), limit))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                tags = []
                try: tags = json.loads(r[5])
                except Exception: tags = []
                results.append({
                    "id": r[0], "ticker": r[1], "company": r[2], "exchange": r[3],
                    "market": r[4], "index_tags": tags, "sector": r[6], "title": r[7],
                    "summary": r[8], "sentiment": r[9], "impact": r[10],
                    "disclosure_type": r[11], "timestamp": r[12], "filing_url": r[13], "source": r[14]
                })
            return results

# Global Singleton Instance
stock_engine = StockNewsEngine()
