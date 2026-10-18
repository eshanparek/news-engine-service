import os
import io
import logging
from datetime import datetime
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("CalendarCardGenerator")

# Standard Market Theme Colors (High-Contrast Financial Infographics)
MARKET_THEMES = {
    "NSE": {
        "header_bg": (30, 58, 138),      # Deep Navy Blue
        "accent": (59, 130, 246),        # Electric Blue
        "flag": "🇮🇳",
        "title": "NSE INDIA EQUITIES & MACRO"
    },
    "BSE": {
        "header_bg": (88, 28, 135),      # Deep Indigo / Purple
        "accent": (147, 51, 234),        # Purple
        "flag": "🇮🇳",
        "title": "BSE INDIA SCRIPS & ACTIONS"
    },
    "MCX": {
        "header_bg": (154, 52, 18),      # Deep Amber / Rust
        "accent": (249, 115, 22),        # Orange
        "flag": "⛽",
        "title": "MCX COMMODITIES & ENERGY"
    },
    "CRYPTO": {
        "header_bg": (180, 83, 9),       # Deep Gold / Bronze
        "accent": (245, 158, 11),        # Amber
        "flag": "₿",
        "title": "CRYPTO ASSETS & SPOT ETFs"
    },
    "NYSE": {
        "header_bg": (15, 76, 129),      # Classic Wall Street Blue
        "accent": (37, 99, 235),         # Royal Blue
        "flag": "🇺🇸",
        "title": "NYSE & US MACRO CALENDAR"
    }
}

class CalendarCardGenerator:
    """
    Renders high-definition, publication-grade PNG info-card graphics for financial calendars.
    Sent directly to Telegram via sendPhoto API so traders can view their daily schedule visually.
    """
    def __init__(self):
        self._init_fonts()

    def _init_fonts(self):
        """Loads available system font or falls back gracefully to default PIL bitmap font."""
        font_paths = [
            "/System/Library/Fonts/SFPro-Bold.ttf",
            "/System/Library/Fonts/SFPro.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        self.font_title = None
        self.font_header = None
        self.font_body = None
        self.font_bold = None
        self.font_mono = None
        self.font_small = None

        for path in font_paths:
            if os.path.exists(path):
                try:
                    self.font_title = ImageFont.truetype(path, 34)
                    self.font_header = ImageFont.truetype(path, 22)
                    self.font_bold = ImageFont.truetype(path, 18)
                    self.font_body = ImageFont.truetype(path, 16)
                    self.font_mono = ImageFont.truetype(path, 15)
                    self.font_small = ImageFont.truetype(path, 13)
                    logger.info(f"Loaded TTF font from {path}")
                    break
                except Exception:
                    continue

        if not self.font_title:
            # Fallback to PIL default font
            default_f = ImageFont.load_default()
            self.font_title = default_f
            self.font_header = default_f
            self.font_bold = default_f
            self.font_body = default_f
            self.font_mono = default_f
            self.font_small = default_f

    def render_market_calendar_card(
        self,
        market: str,
        target_date: str,
        events: List[Dict],
        mode: str = "TODAY",
        holiday_info: Optional[Dict] = None
    ) -> bytes:
        """
        Renders a crisp 1200px-wide infographic card for a regulator/exchange.
        Returns PNG bytes ready for Telegram sendPhoto.
        """
        mkt = market.upper()
        theme = MARKET_THEMES.get(mkt, MARKET_THEMES["NSE"])

        width = 1200
        # Calculate dynamic height based on events count
        header_height = 200
        holiday_height = 110 if holiday_info else 0
        
        # Max events to display on card (clean layout: up to 10 events)
        display_events = events[:12] if events else []
        event_row_height = 100
        events_block_height = max(len(display_events) * event_row_height + 80, 180)
        footer_height = 70

        total_height = header_height + holiday_height + events_block_height + footer_height

        img = Image.new("RGB", (width, total_height), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        # 1. Header Banner
        draw.rectangle([(0, 0), (width, header_height)], fill=theme["header_bg"])
        
        # Header Accent stripe
        draw.rectangle([(0, header_height - 6), (width, header_height)], fill=theme["accent"])

        # Title and Subtitle
        try:
            dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
            date_formatted = dt_obj.strftime("%A, %d %B %Y").upper()
        except Exception:
            date_formatted = target_date

        report_label = "TODAY'S OFFICIAL MARKET CALENDAR" if mode == "TODAY" else "TOMORROW'S LINED-UP SCHEDULE"
        
        draw.text((40, 30), f"{theme['flag']}  {theme['title']}", fill=(255, 255, 255), font=self.font_title)
        draw.text((40, 85), f"📋 {report_label}", fill=(226, 232, 240), font=self.font_header)
        draw.text((40, 130), f"🗓 DATE: {date_formatted}   |   TOTAL EVENTS: {len(events)}", fill=(147, 197, 253), font=self.font_bold)

        current_y = header_height + 20

        # 2. Holiday Banner (if present)
        if holiday_info:
            h_rect = [(30, current_y), (width - 30, current_y + 90)]
            draw.rounded_rectangle(h_rect, radius=10, fill=(254, 242, 242), outline=(239, 68, 68), width=2)
            draw.text((50, current_y + 15), f"🏖️ TRADING HOLIDAY NOTICE ({mkt})", fill=(185, 28, 28), font=self.font_bold)
            draw.text((50, current_y + 45), f"• Occasion: {holiday_info.get('description', '')}", fill=(127, 29, 29), font=self.font_body)
            draw.text((500, current_y + 45), f"• Status: {holiday_info.get('trading_status', 'Closed')}", fill=(127, 29, 29), font=self.font_body)
            current_y += 115

        # 3. Events List Table
        # Section Title
        draw.text((40, current_y), "SCHEDULED CATALYSTS & TIMED ECONOMIC RELEASES", fill=(30, 41, 59), font=self.font_bold)
        current_y += 35

        if not display_events:
            empty_rect = [(30, current_y), (width - 30, current_y + 100)]
            draw.rounded_rectangle(empty_rect, radius=10, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
            draw.text((50, current_y + 35), f"• No scheduled economic releases or corporate filings for {mkt} on this date.", fill=(100, 116, 139), font=self.font_body)
            current_y += 120
        else:
            for idx, e in enumerate(display_events, 1):
                is_high = e.get("impact", "").upper() == "HIGH"
                card_bg = (255, 247, 237) if is_high else ((248, 250, 252) if idx % 2 == 0 else (255, 255, 255))
                card_border = (251, 146, 60) if is_high else (226, 232, 240)
                border_width = 2 if is_high else 1

                row_rect = [(30, current_y), (width - 30, current_y + 88)]
                draw.rounded_rectangle(row_rect, radius=8, fill=card_bg, outline=card_border, width=border_width)

                # Time Badge
                time_str = f"{e.get('time', '10:00')} IST"
                time_badge_rect = [(45, current_y + 12), (160, current_y + 44)]
                t_bg = (234, 88, 12) if is_high else (30, 41, 59)
                draw.rounded_rectangle(time_badge_rect, radius=6, fill=t_bg)
                draw.text((58, current_y + 18), time_str, fill=(255, 255, 255), font=self.font_mono)

                # Impact Badge
                imp_str = "🔥 HIGH IMPACT" if is_high else f"⚡ {e.get('impact', 'MEDIUM')}"
                imp_color = (194, 65, 12) if is_high else (71, 85, 105)
                draw.text((55, current_y + 54), imp_str, fill=imp_color, font=self.font_small)

                # Symbol & Event Title
                sym_str = e.get('symbol', mkt)
                ev_str = e.get('event', 'Scheduled Event')
                full_ev = f"{sym_str} — {ev_str}"
                if len(full_ev) > 65:
                    full_ev = full_ev[:63] + "..."
                draw.text((180, current_y + 14), full_ev, fill=(15, 23, 42), font=self.font_bold)

                # Previous vs Forecast vs Actual
                prev_val = e.get('previous', '—')
                fore_val = e.get('forecast', '—')
                act_val = e.get('actual', '⏳ Pending')
                metrics_str = f"Prev: {prev_val}   |   Est: {fore_val}   |   Actual: {act_val}"
                draw.text((180, current_y + 46), metrics_str, fill=(71, 85, 105), font=self.font_body)

                # Outcome Sentiment Pill
                sent_str = e.get('outcome_sentiment', '⏳ PENDING')
                sent_color = (22, 101, 52) if "BULL" in sent_str else ((153, 27, 27) if "BEAR" in sent_str else (100, 116, 139))
                draw.text((width - 250, current_y + 46), f"Verdict: {sent_str}", fill=sent_color, font=self.font_bold)

                current_y += event_row_height

        # 4. Footer
        draw.line([(30, current_y + 10), (width - 30, current_y + 10)], fill=(226, 232, 240), width=1)
        dispatched_time = datetime.now().strftime("%d %b %Y, %H:%M IST")
        draw.text((40, current_y + 25), f"EPM Pro Multi-Market News & Calendar Engine  •  Generated at {dispatched_time}", fill=(148, 163, 184), font=self.font_small)
        draw.text((width - 320, current_y + 25), "Synchronized with Google Calendar", fill=(37, 99, 235), font=self.font_small)

        # Export to PNG buffer
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue()

calendar_card_generator = CalendarCardGenerator()
