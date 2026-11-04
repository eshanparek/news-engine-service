import sqlite3
import json
from stock_engine import STOCK_DB_FILE

rich_history = [
    # RELIANCE (5 events)
    ("stk_rel_1", "RELIANCE", "Reliance Industries Limited", "NSE", "NSE", 
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYENERGY", "SENSEX"]),
     "Energy, Oil & Gas", "Reliance Inks $10 Billion Green Hydrogen & Solar Gigafactory Framework with Sovereign Wealth Consortium",
     "Strategic long-term partnership to build multi-gigawatt electrolyzer and clean energy manufacturing hub in Gujarat.",
     "BULLISH", "HIGH", "STRATEGIC_DEAL", "2026-11-04 22:15:00", "https://www.nseindia.com", "NSE Corporate Announcements"),
    
    ("stk_rel_2", "RELIANCE", "Reliance Industries Limited", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYENERGY", "SENSEX"]),
     "Energy, Oil & Gas", "Reliance Jio Reports Q2 Net Profit Surge of 14.8% YoY; 5G Subscriber Base Crosses 185 Million",
     "Average revenue per user (ARPU) expands to Rs 195.3, driven by high-tier data plan migrations and enterprise 5G contracts.",
     "BULLISH", "HIGH", "QUARTERLY_RESULTS", "2026-11-03 18:30:00", "https://www.nseindia.com", "NSE Corporate Announcements"),

    ("stk_rel_3", "RELIANCE", "Reliance Industries Limited", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYENERGY", "SENSEX"]),
     "Energy, Oil & Gas", "Reliance Retail Finalizes Acquisition of Major European Fast-Fashion Chain's India Franchise",
     "Expansion of omnichannel luxury footprint with 120 new urban stores slated across metro corridors.",
     "BULLISH", "MEDIUM", "M_AND_A", "2026-11-01 14:10:00", "https://www.bseindia.com", "BSE Announcements"),

    ("stk_rel_4", "RELIANCE", "Reliance Industries Limited", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYENERGY", "SENSEX"]),
     "Energy, Oil & Gas", "Board Meeting Intimation: Consideration of Interim Dividend and Capital Allocation Framework",
     "Meeting of the Board of Directors scheduled to review interim fiscal distribution and petrochemical capex roadmap.",
     "NEUTRAL", "MEDIUM", "BOARD_MEETING", "2026-10-28 11:45:00", "https://www.nseindia.com", "NSE Corporate Announcements"),

    ("stk_rel_5", "RELIANCE", "Reliance Industries Limited", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYENERGY", "SENSEX"]),
     "Energy, Oil & Gas", "Reliance Exploration & Production Secures KG-D6 Deepwater Gas Output Record of 30 MMSCMD",
     "Gas production ramps to meet domestic industrial demand, augmenting sustained EBITDA margins.",
     "BULLISH", "HIGH", "OPERATIONAL_UPDATE", "2026-10-22 09:20:00", "https://www.nseindia.com", "NSE Corporate Announcements"),

    # HDFCBANK (5 events)
    ("stk_hdfc_1", "HDFCBANK", "HDFC Bank Limited", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "BANKNIFTY", "NIFTYFIN", "SENSEX"]),
     "Banking & Financials", "HDFC Bank Reports Q2 Net Advances Up 18.2% YoY; Deposits Expand 15.4% Following Branch Expansion",
     "Gross NPA declines to 1.18% alongside improved loan-deposit ratio and high provision coverage.",
     "BULLISH", "HIGH", "FINANCIAL_RESULTS", "2026-11-04 22:05:00", "https://www.bseindia.com", "BSE Announcements"),

    ("stk_hdfc_2", "HDFCBANK", "HDFC Bank Limited", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "BANKNIFTY", "NIFTYFIN", "SENSEX"]),
     "Banking & Financials", "HDFC Bank Issues USD 750 Million Tier-II Basel III Compliant Bonds at Benchmark Tight Spread",
     "Global bond issuance witnessed 3.8x oversubscription from institutional asset managers across London and Singapore.",
     "BULLISH", "MEDIUM", "BOND_ISSUANCE", "2026-11-02 16:15:00", "https://www.nseindia.com", "NSE Corporate Announcements"),

    ("stk_hdfc_3", "HDFCBANK", "HDFC Bank Limited", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "BANKNIFTY", "NIFTYFIN", "SENSEX"]),
     "Banking & Financials", "RBI Clears Appointment of Key Executive Directors for Retail Assets and Treasury Operations",
     "Central bank grants regulatory clearance for corporate restructuring of wholesale asset divisions.",
     "NEUTRAL", "MEDIUM", "REGULATORY_APPROVAL", "2026-10-29 19:40:00", "https://www.rbi.org.in", "RBI Directives"),

    ("stk_hdfc_4", "HDFCBANK", "HDFC Bank Limited", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "BANKNIFTY", "NIFTYFIN", "SENSEX"]),
     "Banking & Financials", "HDFC Bank Accelerates Co-Branded Institutional Credit Card Program with Premier Tech Platforms",
     "Partnership projected to onboard 2.5 million new salaried cardholders over the next four quarters.",
     "BULLISH", "MEDIUM", "PRODUCT_LAUNCH", "2026-10-24 13:00:00", "https://www.bseindia.com", "BSE Announcements"),

    ("stk_hdfc_5", "HDFCBANK", "HDFC Bank Limited", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "BANKNIFTY", "NIFTYFIN", "SENSEX"]),
     "Banking & Financials", "Clarification on Media Reports Regarding Mortgage Loan Book Harmonization Post-Merger",
     "Bank clarifies seamless asset integration with no credit quality deterioration across legacy home loan portfolios.",
     "NEUTRAL", "LOW", "EXCHANGE_CLARIFICATION", "2026-10-18 10:30:00", "https://www.nseindia.com", "NSE Corporate Announcements"),

    # TCS (5 events)
    ("stk_tcs_1", "TCS", "Tata Consultancy Services", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYIT", "SENSEX"]),
     "IT & Technology", "TCS Bags $1.2 Billion Multi-Year Cloud & AI Modernization Deal with European Banking Conglomerate",
     "TCS to deploy proprietary Cognix platform and generative AI microservices across 14 European markets.",
     "BULLISH", "HIGH", "CONTRACT_WIN", "2026-11-04 21:50:00", "https://www.nseindia.com", "NSE Corporate Announcements"),

    ("stk_tcs_2", "TCS", "Tata Consultancy Services", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYIT", "SENSEX"]),
     "IT & Technology", "TCS Announces Strategic GenAI Engineering Hub Expansion in Tokyo and Singapore",
     "New enterprise center to support high-performance industrial robotics and quantum computing applications.",
     "BULLISH", "MEDIUM", "EXPANSION", "2026-11-02 12:00:00", "https://www.bseindia.com", "BSE Announcements"),

    ("stk_tcs_3", "TCS", "Tata Consultancy Services", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYIT", "SENSEX"]),
     "IT & Technology", "TCS Recognized as Global Leader in Everest Group's Banking IT Services PEAK Matrix 2026",
     "Independent assessment highlights TCS BaNCS platform scale and unmatched enterprise delivery track record.",
     "BULLISH", "LOW", "INDUSTRY_AWARD", "2026-10-27 15:20:00", "https://www.nseindia.com", "NSE Corporate Announcements"),

    ("stk_tcs_4", "TCS", "Tata Consultancy Services", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYIT", "SENSEX"]),
     "IT & Technology", "Record Date for Second Interim Dividend of Rs 10 Per Equity Share Disclosed",
     "Dividend payout disbursable to all equity holders on company registry as of the record date.",
     "NEUTRAL", "MEDIUM", "DIVIDEND_FILING", "2026-10-20 17:00:00", "https://www.bseindia.com", "BSE Announcements"),

    ("stk_tcs_5", "TCS", "Tata Consultancy Services", "NSE", "NSE",
     json.dumps(["NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500", "NIFTYIT", "SENSEX"]),
     "IT & Technology", "TCS Empanelled by North American Aerospace Consortium for Autonomous Cyber Defense Systems",
     "Five-year agreement encompassing zero-trust architecture and automated operational threat triage.",
     "BULLISH", "HIGH", "CONTRACT_WIN", "2026-10-15 14:15:00", "https://www.nseindia.com", "NSE Corporate Announcements"),

    # CRUDEOIL (5 events)
    ("stk_crude_1", "CRUDEOIL", "MCX Crude Oil", "MCX", "MCX",
     json.dumps(["MCXENERGY"]),
     "Energy, Oil & Gas", "OPEC+ Extends Voluntary Supply Restraints of 2.2M BPD into Q1 2027; MCX Crude Contracts Rally 2.4%",
     "Crude oil futures surged as energy ministers confirmed strict quota compliance and extended output discipline.",
     "BULLISH", "HIGH", "COMMODITY_CATALYST", "2026-11-04 21:30:00", "https://www.mcxindia.com", "MCX Commodity Wire"),

    ("stk_crude_2", "CRUDEOIL", "MCX Crude Oil", "MCX", "MCX",
     json.dumps(["MCXENERGY"]),
     "Energy, Oil & Gas", "US Strategic Petroleum Reserve (SPR) Repurchase Notice: DOE Solicits 4.5M Barrels for Gulf Coast Sites",
     "Physical inventory drawdowns reinforce firm prompt backwardation in near-month delivery contracts.",
     "BULLISH", "MEDIUM", "INVENTORY_REPORT", "2026-11-02 20:45:00", "https://www.eia.gov", "US EIA Petroleum Data"),

    ("stk_crude_3", "CRUDEOIL", "MCX Crude Oil", "MCX", "MCX",
     json.dumps(["MCXENERGY"]),
     "Energy, Oil & Gas", "EIA Weekly Petroleum Status Report: Commercial Crude Inventories Fall by 3.2M Barrels vs Expected Build",
     "Refinery utilization rates jump to 92.4% as domestic gasoline and distillate demand rebounds.",
     "BULLISH", "HIGH", "EIA_REPORT", "2026-10-30 20:00:00", "https://www.mcxindia.com", "MCX Market Intelligence"),

    ("stk_crude_4", "CRUDEOIL", "MCX Crude Oil", "MCX", "MCX",
     json.dumps(["MCXENERGY"]),
     "Energy, Oil & Gas", "MCX Circular: Revision in Margin Framework and Calendar Spread Benefit on Crude Oil Futures",
     "Exchange revises initial margin requirement to 12.5% to align with international volatility standards.",
     "NEUTRAL", "MEDIUM", "EXCHANGE_CIRCULAR", "2026-10-25 18:00:00", "https://www.mcxindia.com", "MCX Circulars"),

    ("stk_crude_5", "CRUDEOIL", "MCX Crude Oil", "MCX", "MCX",
     json.dumps(["MCXENERGY"]),
     "Energy, Oil & Gas", "Geopolitical Chokepoint Advisory: Red Sea Tanker Transit Rerouting Increases Spot Freight Rates",
     "Additional sailing days around Cape of Good Hope add $1.80/bbl landed crude premium into Asian refiners.",
     "BULLISH", "HIGH", "GEOPOLITICAL_ALERT", "2026-10-19 11:30:00", "https://www.mcxindia.com", "MCX Commodity Wire"),

    # NVDA (5 events)
    ("stk_nvda_1", "NVDA", "NVIDIA Corporation", "NASDAQ", "NASDAQ",
     json.dumps(["NDX", "SPX"]),
     "IT & Technology", "NVIDIA Form 8-K: Blackwell Ultra GPU Architecture Exceeds Delivery Targets; SEC Edgar Filing",
     "Nvidia files Form 8-K detailing cloud enterprise orders exceeding $22B for next-generation AI infrastructure clusters.",
     "BULLISH", "HIGH", "SEC_EDGAR_FILING", "2026-11-04 20:45:00", "https://www.sec.gov/edgar", "SEC EDGAR"),

    ("stk_nvda_2", "NVDA", "NVIDIA Corporation", "NASDAQ", "NASDAQ",
     json.dumps(["NDX", "SPX"]),
     "IT & Technology", "NVIDIA Announces Co-Packaged Optics Breakthrough with Leading Foundry Partners for Exascale Networking",
     "Quantum optical interconnects reduce datacenter power consumption by 35% across multi-rack compute topologies.",
     "BULLISH", "HIGH", "TECH_INNOVATION", "2026-11-01 17:30:00", "https://www.sec.gov/edgar", "SEC EDGAR"),

    ("stk_nvda_3", "NVDA", "NVIDIA Corporation", "NASDAQ", "NASDAQ",
     json.dumps(["NDX", "SPX"]),
     "IT & Technology", "Form 4 Statement of Changes in Beneficial Ownership Filed with US SEC",
     "Scheduled executive Rule 10b5-1 trading plan execution filed with zero discretionary off-market block sales.",
     "NEUTRAL", "LOW", "INSIDER_FILING", "2026-10-29 21:00:00", "https://www.sec.gov/edgar", "SEC EDGAR"),

    ("stk_nvda_4", "NVDA", "NVIDIA Corporation", "NASDAQ", "NASDAQ",
     json.dumps(["NDX", "SPX"]),
     "IT & Technology", "NVIDIA Inks Multi-Billion Sovereign AI Infrastructure Partnership with Middle East Telecom Consortium",
     "Deployment of sovereign compute clusters optimized for regional multilingual language models.",
     "BULLISH", "HIGH", "STRATEGIC_DEAL", "2026-10-23 15:45:00", "https://www.sec.gov/edgar", "SEC EDGAR"),

    ("stk_nvda_5", "NVDA", "NVIDIA Corporation", "NASDAQ", "NASDAQ",
     json.dumps(["NDX", "SPX"]),
     "IT & Technology", "Form 10-Q Quarterly Filing Discloses Cash and Liquid Marketable Securities of $34.8 Billion",
     "Robust operating cash flow supports sustained R&D acceleration into next-generation silicon design.",
     "BULLISH", "MEDIUM", "QUARTERLY_FILING", "2026-10-16 19:30:00", "https://www.sec.gov/edgar", "SEC EDGAR"),

    # GOLD (5 events)
    ("stk_gold_1", "GOLD", "MCX Gold Futures", "MCX", "MCX",
     json.dumps(["MCXBULLDEX"]),
     "Commodities", "Central Bank Sovereign Bullion Reserves Accumulation Hits Record 1,200 Tonnes; Gold Tests Fresh Highs",
     "Sovereign reserve rebalancing drives institutional physical delivery demand on MCX bullion delivery vaults.",
     "BULLISH", "MEDIUM", "COMMODITY_CATALYST", "2026-11-04 20:00:00", "https://www.mcxindia.com", "MCX Market Intelligence"),

    ("stk_gold_2", "GOLD", "MCX Gold Futures", "MCX", "MCX",
     json.dumps(["MCXBULLDEX"]),
     "Commodities", "World Gold Council Report: Global Gold Demand Reaches Record $100 Billion Value in Q3",
     "ETF inflows and institutional portfolio hedging offset softer retail jewelry demand in festive season.",
     "BULLISH", "HIGH", "INDUSTRY_REPORT", "2026-11-02 14:00:00", "https://www.gold.org", "World Gold Council"),

    ("stk_gold_3", "GOLD", "MCX Gold Futures", "MCX", "MCX",
     json.dumps(["MCXBULLDEX"]),
     "Commodities", "US Real Yields Dip Below 1.65% Post Fed Signals; Institutional Bullion Allocations Accelerate",
     "Inverse correlation with real interest rates prompts major asset managers to increase gold weightings to 8%.",
     "BULLISH", "HIGH", "MACRO_CATALYST", "2026-10-28 16:30:00", "https://www.mcxindia.com", "MCX Commodity Wire"),

    ("stk_gold_4", "GOLD", "MCX Gold Futures", "MCX", "MCX",
     json.dumps(["MCXBULLDEX"]),
     "Commodities", "MCX Bullion Vaults Report 100% Delivery Settlement in October Expiry Contract",
     "Physical delivery mechanism operates smoothly with accredited refinery bars meeting Good Delivery standards.",
     "NEUTRAL", "LOW", "OPERATIONAL_UPDATE", "2026-10-25 12:15:00", "https://www.mcxindia.com", "MCX Circulars"),

    ("stk_gold_5", "GOLD", "MCX Gold Futures", "MCX", "MCX",
     json.dumps(["MCXBULLDEX"]),
     "Commodities", "Diwali Dhanteras Advance Bookings Jump 22% Across Major Indian Bullion Exchanges",
     "Consumer pre-booking schemes lock in current prices ahead of peak wedding season requirements.",
     "BULLISH", "MEDIUM", "SEASONAL_DEMAND", "2026-10-18 10:00:00", "https://www.mcxindia.com", "MCX Market Intelligence")
]

with sqlite3.connect(STOCK_DB_FILE) as conn:
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS stock_disclosures (id TEXT PRIMARY KEY, ticker TEXT, company TEXT, exchange TEXT, market TEXT, index_tags TEXT, sector TEXT, title TEXT, summary TEXT, sentiment TEXT, impact TEXT, disclosure_type TEXT, timestamp TEXT, filing_url TEXT, source TEXT)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_ticker ON stock_disclosures(ticker)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_market ON stock_disclosures(market)")
    for item in rich_history:
        cursor.execute("INSERT OR REPLACE INTO stock_disclosures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", item)
    conn.commit()

print(f"Successfully seeded {len(rich_history)} rich disclosures across tickers!")
