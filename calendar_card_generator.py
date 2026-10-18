import os
import io
import logging
from datetime import datetime
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("CalendarCardGenerator")

# Standard Market Theme Colors (2035 High-Contrast Cyber-Financial Infographics)
MARKET_THEMES = {
    "NSE": {
        "header_bg": (15, 23, 42),       # Dark Slate Obsidian
        "gradient_to": (30, 58, 138),    # Deep Navy Blue
        "accent": (59, 130, 246),        # Electric Azure Blue
        "flag": "🇮🇳",
        "title": "NSE INDIA — ALL EQUITIES & MACRO",
        "scope": "National Stock Exchange of India (Mainboard, SME & F&O)",
        "hours": "09:15 – 15:30 IST"
    },
    "BSE": {
        "header_bg": (24, 16, 47),       # Dark Obsidian Indigo
        "gradient_to": (88, 28, 135),    # Deep Purple
        "accent": (168, 85, 247),        # Neon Purple
        "flag": "🇮🇳",
        "title": "BSE INDIA — ALL LISTED SCRIPS & ACTIONS",
        "scope": "Bombay Stock Exchange (Corporate Actions, Filings & Boards)",
        "hours": "09:15 – 15:30 IST"
    },
    "MCX": {
        "header_bg": (28, 25, 23),       # Dark Stone Bronze
        "gradient_to": (120, 53, 15),    # Deep Amber/Rust
        "accent": (245, 158, 11),        # Radiant Amber/Gold
        "flag": "⛽",
        "title": "MCX INDIA — BULLION, ENERGY & METALS",
        "scope": "Multi Commodity Exchange of India (Commodities & Derivatives)",
        "hours": "09:00 – 23:30/23:55 IST"
    },
    "CRYPTO": {
        "header_bg": (9, 9, 11),         # Cyber Space Black
        "gradient_to": (39, 39, 42),     # Zinc Charcoal
        "accent": (234, 179, 8),         # Cyber Gold / Yellow
        "flag": "₿",
        "title": "CRYPTO MARKETS — ASSETS & SPOT ETFs",
        "scope": "Global Digital Assets, Bitcoin/Ethereum ETFs & Derivatives",
        "hours": "24/7 Continuous (00:00 – 23:59 IST)"
    },
    "NYSE": {
        "header_bg": (3, 7, 18),         # Deepest Midnight
        "gradient_to": (23, 37, 84),     # Deep Wall Street Blue
        "accent": (37, 99, 235),         # Electric Royal Blue
        "flag": "🇺🇸",
        "title": "NYSE & US MACRO — EARNINGS & FED",
        "scope": "New York Stock Exchange, Nasdaq & US Federal Reserve Releases",
        "hours": "19:00 – 01:30 IST (Pre-Market 13:30 IST)"
    }
}

class CalendarCardGenerator:
    """
    Renders 2035 publication-grade high-contrast infographic cards for financial calendars.
    Optimized for Telegram sendPhoto so traders can view their daily schedule visually in ultra-crisp resolution.
    """
    def __init__(self):
        self._init_fonts()

    def _init_fonts(self):
        """Loads bundled or system TrueType fonts for ultra-crisp high-DPI rendering."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        font_paths = [
            os.path.join(base_dir, "assets", "fonts", "Arial Bold.ttf"),
            os.path.join(base_dir, "assets", "fonts", "Arial.ttf"),
            "assets/fonts/Arial Bold.ttf",
            "assets/fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
        ]
        self.font_title = None
        self.font_header = None
        self.font_sub = None
        self.font_bold = None
        self.font_body = None
        self.font_mono = None
        self.font_small = None
        self.font_micro = None

        for path in font_paths:
            if os.path.exists(path):
                try:
                    self.font_title = ImageFont.truetype(path, 34)
                    self.font_header = ImageFont.truetype(path, 22)
                    self.font_sub = ImageFont.truetype(path, 16)
                    self.font_bold = ImageFont.truetype(path, 17)
                    self.font_body = ImageFont.truetype(path, 15)
                    self.font_mono = ImageFont.truetype(path, 16)
                    self.font_small = ImageFont.truetype(path, 13)
                    self.font_micro = ImageFont.truetype(path, 11)
                    logger.info(f"Loaded TTF font for cards from: {path}")
                    break
                except Exception as e:
                    logger.warning(f"Failed loading font from {path}: {e}")
                    continue

        if not self.font_title:
            default_f = ImageFont.load_default()
            self.font_title = default_f
            self.font_header = default_f
            self.font_sub = default_f
            self.font_bold = default_f
            self.font_body = default_f
            self.font_mono = default_f
            self.font_small = default_f
            self.font_micro = default_f

    def render_market_calendar_card(
        self,
        market: str,
        target_date: str,
        events: List[Dict],
        mode: str = "TODAY",
        holiday_info: Optional[Dict] = None
    ) -> bytes:
        """
        Renders a 2035 publication-grade 1200px-wide infographic card for a regulator/exchange.
        Bakes in complete schedule details, timing, impact, benchmarks, and verdicts.
        """
        mkt = market.upper()
        theme = MARKET_THEMES.get(mkt, MARKET_THEMES["NSE"])

        width = 1200
        header_height = 220
        holiday_height = 120 if holiday_info else 0
        stats_ribbon_height = 60

        # Sort events: High impact first, then by time
        sorted_events = sorted(
            events or [],
            key=lambda x: (0 if x.get("impact", "").upper() == "HIGH" else 1, x.get("time", "99:99"))
        )

        # Show up to 18 events cleanly on card; summarize if more
        max_events_to_show = 18
        display_events = sorted_events[:max_events_to_show]
        remaining_count = max(0, len(sorted_events) - max_events_to_show)

        # Dynamic row height: spacious for few events, high-density for many
        if len(display_events) <= 4:
            event_row_height = 110
        elif len(display_events) <= 8:
            event_row_height = 96
        else:
            event_row_height = 84

        events_block_height = max(len(display_events) * event_row_height + 90, 200)
        if remaining_count > 0:
            events_block_height += 60

        footer_height = 80
        total_height = header_height + holiday_height + stats_ribbon_height + events_block_height + footer_height

        # Base Canvas: Pure crisp white background (#FFFFFF)
        img = Image.new("RGB", (width, total_height), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        # ── 1. Futuristic Header Banner ──
        draw.rectangle([(0, 0), (width, header_height)], fill=theme["header_bg"])
        # Top Accent neon bar
        draw.rectangle([(0, 0), (width, 6)], fill=theme["accent"])
        # Bottom Accent neon bar
        draw.rectangle([(0, header_height - 5), (width, header_height)], fill=theme["accent"])

        # Title and Subtitles
        try:
            dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
            date_formatted = dt_obj.strftime("%A, %d %B %Y").upper()
        except Exception:
            date_formatted = target_date

        report_label = "OFFICIAL DAILY SCHEDULE & TIMERS" if mode == "TODAY" else "TOMORROW'S LINED-UP SCHEDULE"

        # Market Flag & Title
        draw.text((45, 28), f"{theme['flag']}  {theme['title']}", fill=(255, 255, 255), font=self.font_title)
        draw.text((45, 82), f"⚡ {theme['scope']}", fill=(203, 213, 225), font=self.font_sub)
        draw.text((45, 114), f"⏰ Trading Hours: {theme['hours']}   |   Timezone: Indian Standard Time (IST)", fill=(148, 163, 184), font=self.font_small)

        # Date & Mode Capsule (Top Right)
        mode_pill_bg = (30, 41, 59)
        draw.rounded_rectangle([(width - 390, 28), (width - 45, 84)], radius=8, fill=mode_pill_bg, outline=theme["accent"], width=2)
        draw.text((width - 375, 38), f"📋 {report_label}", fill=(255, 255, 255), font=self.font_bold)
        draw.text((width - 375, 62), f"🗓 {date_formatted}", fill=(147, 197, 253), font=self.font_small)

        current_y = header_height

        # ── 2. Holiday Warning Banner (if market closed) ──
        if holiday_info:
            h_rect = [(40, current_y + 15), (width - 40, current_y + 105)]
            draw.rounded_rectangle(h_rect, radius=10, fill=(254, 242, 242), outline=(220, 38, 38), width=2)
            draw.text((65, current_y + 28), f"🏖️ TRADING HOLIDAY NOTICE — {mkt} CLOSED / SPECIAL SESSION", fill=(185, 28, 28), font=self.font_bold)
            draw.text((65, current_y + 58), f"• Occasion: {holiday_info.get('description', 'Official Market Holiday')}", fill=(127, 29, 29), font=self.font_body)
            draw.text((580, current_y + 58), f"• Trading Session Status: {holiday_info.get('trading_status', 'Closed')}", fill=(153, 27, 27), font=self.font_bold)
            current_y += holiday_height

        # ── 3. High-Tech Statistics Ribbon ──
        high_impact_count = sum(1 for e in sorted_events if e.get("impact", "").upper() == "HIGH")
        draw.rectangle([(0, current_y), (width, current_y + stats_ribbon_height)], fill=(248, 250, 252))
        draw.line([(0, current_y + stats_ribbon_height), (width, current_y + stats_ribbon_height)], fill=(226, 232, 240), width=1)

        # Stats pills
        draw.text((45, current_y + 18), f"📊 TOTAL CATALYSTS: {len(sorted_events)}", fill=(15, 23, 42), font=self.font_bold)
        draw.text((320, current_y + 18), f"🔥 HIGH-IMPACT BENCHMARKS: {high_impact_count}", fill=(220, 38, 38) if high_impact_count > 0 else (71, 85, 105), font=self.font_bold)
        session_str = "🏖️ HOLIDAY (CLOSED)" if holiday_info else "🟢 REGULAR TRADING ACTIVE"
        draw.text((680, current_y + 18), f"🏛 STATUS: {session_str}", fill=(22, 101, 52) if not holiday_info else (185, 28, 28), font=self.font_bold)
        draw.text((width - 250, current_y + 18), "⚡ LIVE VERIFIED WIRE", fill=theme["accent"], font=self.font_bold)

        current_y += stats_ribbon_height + 25

        # ── 4. Section Title ──
        draw.text((45, current_y), f"SCHEDULED ECONOMIC RELEASES & CORPORATE ACTIONS ({mkt})", fill=(15, 23, 42), font=self.font_bold)
        draw.text((width - 340, current_y + 4), "Indian Standard Time (IST) Timings", fill=(100, 116, 139), font=self.font_small)
        current_y += 35

        # ── 5. Events List Cards ──
        if not display_events:
            empty_rect = [(40, current_y), (width - 40, current_y + 120)]
            draw.rounded_rectangle(empty_rect, radius=10, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
            draw.text((65, current_y + 45), f"• No official scheduled catalysts or corporate releases found for {mkt} on {date_formatted}.", fill=(100, 116, 139), font=self.font_bold)
            draw.text((65, current_y + 75), "• Regular secondary market liquidity and order books continue as scheduled.", fill=(148, 163, 184), font=self.font_body)
            current_y += 140
        else:
            for idx, e in enumerate(display_events, 1):
                is_high = e.get("impact", "").upper() == "HIGH"
                card_bg = (255, 247, 237) if is_high else ((248, 250, 252) if idx % 2 == 0 else (255, 255, 255))
                card_border = (251, 146, 60) if is_high else (226, 232, 240)
                border_width = 2 if is_high else 1

                row_h = event_row_height - 12
                row_rect = [(40, current_y), (width - 40, current_y + row_h)]
                draw.rounded_rectangle(row_rect, radius=8, fill=card_bg, outline=card_border, width=border_width)

                # Time Badge (IST)
                time_str = f"{e.get('time', '10:00')} IST"
                time_badge_rect = [(52, current_y + 10), (175, current_y + 42)]
                t_bg = (220, 38, 38) if is_high else (15, 23, 42)
                draw.rounded_rectangle(time_badge_rect, radius=6, fill=t_bg)
                draw.text((62, current_y + 16), time_str, fill=(255, 255, 255), font=self.font_mono)

                # Impact Tag
                imp_str = "🔥 HIGH IMPACT" if is_high else f"⚡ {e.get('impact', 'MEDIUM')}"
                imp_color = (194, 65, 12) if is_high else (71, 85, 105)
                draw.text((60, current_y + 50), imp_str, fill=imp_color, font=self.font_small)

                # Symbol Pill
                sym_str = str(e.get("symbol", mkt)).strip()
                if sym_str.startswith("🇮🇳") or sym_str.startswith("🇺🇸") or sym_str.startswith("⛽") or sym_str.startswith("₿"):
                    clean_sym = sym_str.split(":", 1)[-1].strip() if ":" in sym_str else sym_str[2:].strip()
                else:
                    clean_sym = sym_str

                # Event Title
                ev_str = str(e.get("event", "Scheduled Release")).strip()
                full_ev = f"{clean_sym} — {ev_str}"
                max_title_chars = 68 if width == 1200 else 55
                if len(full_ev) > max_title_chars:
                    full_ev = full_ev[:max_title_chars - 3] + "..."

                draw.text((195, current_y + 12), full_ev, fill=(15, 23, 42), font=self.font_bold)

                # Financial Metrics: Prev vs Forecast vs Actual
                prev_val = str(e.get("previous", "—"))
                fore_val = str(e.get("forecast", "—"))
                act_val = str(e.get("actual", "⏳ Pending"))
                metrics_str = f"Prev: {prev_val}   |   Consensus: {fore_val}   |   Actual: {act_val}"
                draw.text((195, current_y + 46), metrics_str, fill=(71, 85, 105), font=self.font_body)

                # Verdict / Sentiment Badge
                sent_str = str(e.get("outcome_sentiment", "⏳ PENDING")).strip()
                sent_color = (22, 101, 52) if "BULL" in sent_str else ((185, 28, 28) if "BEAR" in sent_str else (100, 116, 139))
                draw.text((width - 240, current_y + 46), f"Verdict: {sent_str}", fill=sent_color, font=self.font_bold)

                current_y += event_row_height

            # Indicator if there are more events scheduled
            if remaining_count > 0:
                more_rect = [(40, current_y), (width - 40, current_y + 46)]
                draw.rounded_rectangle(more_rect, radius=8, fill=(241, 245, 249), outline=(203, 213, 225), width=1)
                draw.text((60, current_y + 13), f"⚡ +{remaining_count} MORE {mkt} CORPORATE ACTIONS & RELEASES SCHEDULED FOR THIS DATE", fill=(71, 85, 105), font=self.font_bold)
                draw.text((width - 380, current_y + 13), "Access complete ledger on EPM Pro Web Terminal", fill=theme["accent"], font=self.font_small)
                current_y += 60

        # ── 6. Futuristic Terminal Footer ──
        draw.line([(40, current_y + 15), (width - 40, current_y + 15)], fill=(226, 232, 240), width=1)
        dispatched_time = datetime.now().strftime("%d %b %Y, %H:%M:%S IST")
        draw.text((45, current_y + 30), f"EPM Pro Multi-Market Intelligence Engine  •  Verified Output at {dispatched_time}", fill=(148, 163, 184), font=self.font_small)
        draw.text((width - 420, current_y + 30), "📅 Synchronized with Google Calendar (60m Prior Alarms)", fill=(37, 99, 235), font=self.font_bold)

        # Export to optimized PNG buffer
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue()

calendar_card_generator = CalendarCardGenerator()
