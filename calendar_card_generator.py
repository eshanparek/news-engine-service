import os
import io
import re
import math
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("CalendarCardGenerator")

# Standard Market Theme Colors (2035 High-Contrast Cyber-Financial Infographics)
MARKET_THEMES = {
    "NSE": {
        "header_bg": (15, 23, 42),       # Dark Slate Obsidian
        "gradient_to": (30, 58, 138),    # Deep Navy Blue
        "accent": (59, 130, 246),        # Electric Azure Blue
        "badge": "NSE",
        "title": "NSE INDIA — ALL EQUITIES & MACRO",
        "scope": "National Stock Exchange of India (Mainboard, SME & F&O)",
        "hours": "09:15 – 15:30 IST"
    },
    "BSE": {
        "header_bg": (24, 16, 47),       # Dark Obsidian Indigo
        "gradient_to": (88, 28, 135),    # Deep Purple
        "accent": (168, 85, 247),        # Neon Purple
        "badge": "BSE",
        "title": "BSE INDIA — ALL LISTED SCRIPS & ACTIONS",
        "scope": "Bombay Stock Exchange (Corporate Actions, Filings & Boards)",
        "hours": "09:15 – 15:30 IST"
    },
    "MCX": {
        "header_bg": (28, 25, 23),       # Dark Stone Bronze
        "gradient_to": (120, 53, 15),    # Deep Amber/Rust
        "accent": (245, 158, 11),        # Radiant Amber/Gold
        "badge": "MCX",
        "title": "MCX INDIA — BULLION, ENERGY & METALS",
        "scope": "Multi Commodity Exchange of India (Commodities & Derivatives)",
        "hours": "09:00 – 23:30/23:55 IST"
    },
    "CRYPTO": {
        "header_bg": (9, 9, 11),         # Cyber Space Black
        "gradient_to": (39, 39, 42),     # Zinc Charcoal
        "accent": (234, 179, 8),         # Cyber Gold / Yellow
        "badge": "CRYPTO",
        "title": "CRYPTO MARKETS — ASSETS & SPOT ETFs",
        "scope": "Global Digital Assets, Bitcoin/Ethereum ETFs & Derivatives",
        "hours": "24/7 Continuous (00:00 – 23:59 IST)"
    },
    "NYSE": {
        "header_bg": (3, 7, 18),         # Deepest Midnight
        "gradient_to": (23, 37, 84),     # Deep Wall Street Blue
        "accent": (37, 99, 235),         # Electric Royal Blue
        "badge": "NYSE",
        "title": "NYSE & US MACRO — EARNINGS & FED",
        "scope": "New York Stock Exchange, Nasdaq & US Federal Reserve Releases",
        "hours": "19:00 – 01:30 IST (Pre-Market 13:30 IST)"
    }
}

EMOJI_CLEAN_REGEX = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\u25b6\u25c0\ufe0f]+",
    flags=re.UNICODE
)

def clean_text_for_image(text: str) -> str:
    """Strips emoji codepoints that would otherwise render as missing character tofu boxes (□) in PIL."""
    if not text:
        return ""
    cleaned = EMOJI_CLEAN_REGEX.sub("", str(text))
    return re.sub(r"\s+", " ", cleaned).strip()


class CalendarCardGenerator:
    """
    Renders 2035 publication-grade high-contrast infographic cards for financial calendars.
    Supports dynamic pagination so NO events are hidden or omitted when schedules are long.
    """
    def __init__(self):
        self._init_fonts()
        self._init_logo()

    def _init_logo(self):
        """Loads and prepares the official Global News Feed Room circular broadcast logo."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(base_dir, "assets", "global_news_feed_room_logo.png")
        if not os.path.exists(logo_path):
            logo_path = "assets/global_news_feed_room_logo.png"
        if os.path.exists(logo_path):
            try:
                self.logo_img = Image.open(logo_path).convert("RGBA")
                logger.info(f"Loaded Global News Feed Room logo for calendar: {logo_path}")
            except Exception as e:
                logger.warning(f"Could not load calendar logo from {logo_path}: {e}")
                self.logo_img = None
        else:
            self.logo_img = None

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
                    self.font_title = ImageFont.truetype(path, 23)
                    self.font_header = ImageFont.truetype(path, 21)
                    self.font_sub = ImageFont.truetype(path, 15)
                    self.font_bold = ImageFont.truetype(path, 15)
                    self.font_body = ImageFont.truetype(path, 14)
                    self.font_mono = ImageFont.truetype(path, 15)
                    self.font_small = ImageFont.truetype(path, 12)
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

    def chunk_events_for_cards(self, events: List[Dict], max_per_page: int = 15) -> List[Tuple[List[Dict], int, int]]:
        """
        Splits events into balanced pages so no page is overloaded or has hidden overflow.
        Returns list of (page_events, start_index_1_based, end_index_1_based).
        """
        if not events:
            return [([], 0, 0)]
        total = len(events)
        if total <= max_per_page:
            return [(events, 1, total)]

        num_pages = math.ceil(total / max_per_page)
        avg_per_page = math.ceil(total / num_pages)
        pages = []
        start = 0
        while start < total:
            end = min(start + avg_per_page, total)
            pages.append((events[start:end], start + 1, end))
            start = end
        return pages

    def render_single_page(
        self,
        market: str,
        target_date: str,
        page_events: List[Dict],
        total_events_count: int,
        high_impact_count: int,
        start_idx: int,
        end_idx: int,
        page_num: int,
        total_pages: int,
        mode: str = "TODAY",
        holiday_info: Optional[Dict] = None
    ) -> bytes:
        """
        Renders a single 1200px-wide high-contrast infographic card page.
        Guarantees zero tofu boxes (□) and clean alignment.
        """
        mkt = market.upper()
        theme = MARKET_THEMES.get(mkt, MARKET_THEMES["NSE"])

        width = 1200
        header_height = 205
        holiday_height = 110 if (holiday_info and page_num == 1) else 0
        stats_ribbon_height = 54

        # Dynamic row height based on events on this page
        if len(page_events) <= 4:
            event_row_height = 105
        elif len(page_events) <= 8:
            event_row_height = 94
        else:
            event_row_height = 84

        events_block_height = max(len(page_events) * event_row_height + 85, 200)
        nav_banner_height = 54 if total_pages > 1 else 0
        footer_height = 96
        total_height = header_height + holiday_height + stats_ribbon_height + events_block_height + nav_banner_height + footer_height

        # Base Canvas: Pure crisp white background (#FFFFFF)
        img = Image.new("RGB", (width, total_height), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        # ── 1. Futuristic Header Banner ──
        draw.rectangle([(0, 0), (width, header_height)], fill=theme["header_bg"])
        # Top Accent neon bar
        draw.rectangle([(0, 0), (width, 5)], fill=theme["accent"])
        # Bottom Accent neon bar
        draw.rectangle([(0, header_height - 4), (width, header_height)], fill=theme["accent"])

        # Title and Subtitles
        try:
            dt_obj = datetime.strptime(target_date, "%Y-%m-%d")
            date_formatted = dt_obj.strftime("%A, %d %B %Y").upper()
        except Exception:
            date_formatted = target_date

        report_label = "DAILY SCHEDULE & TIMERS" if mode == "TODAY" else "TOMORROW'S SCHEDULE"

        # Market Badge Pill (Eliminates flag emoji tofu boxes)
        badge_w = 80
        draw.rounded_rectangle([(45, 26), (45 + badge_w, 64)], radius=6, fill=theme["accent"])
        draw.text((58, 33), theme["badge"], fill=(255, 255, 255), font=self.font_bold)

        # Title (Strictly bounded so it never collides with capsule)
        draw.text((45 + badge_w + 14, 32), clean_text_for_image(theme["title"]), fill=(255, 255, 255), font=self.font_title)
        draw.text((45, 102), f"Scope: {clean_text_for_image(theme['scope'])}", fill=(203, 213, 225), font=self.font_sub)
        draw.text((45, 130), f"Trading Hours: {theme['hours']}   |   Timezone: Indian Standard Time (IST)", fill=(148, 163, 184), font=self.font_small)

        # Top Right Corner: Global News Feed Room Broadcast TV Bug Logo
        if getattr(self, "logo_img", None):
            logo_size = 88
            logo_resized = self.logo_img.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            logo_x = width - 45 - logo_size
            logo_y = 20
            img.paste(logo_resized, (logo_x, logo_y), mask=logo_resized)
            capsule_right = logo_x - 14
        else:
            capsule_right = width - 45

        # Date & Page Capsule (Top Right, beside Logo)
        mode_pill_bg = (30, 41, 59)
        capsule_w = 330
        capsule_left = capsule_right - capsule_w
        draw.rounded_rectangle([(capsule_left, 24), (capsule_right, 86)], radius=8, fill=mode_pill_bg, outline=theme["accent"], width=2)
        draw.text((capsule_left + 14, 33), f"REPORT: {report_label}", fill=(255, 255, 255), font=self.font_bold)
        page_suffix = f"  |  PG {page_num}/{total_pages}" if total_pages > 1 else ""
        draw.text((capsule_left + 14, 57), f"DATE: {date_formatted}{page_suffix}", fill=(147, 197, 253), font=self.font_small)

        current_y = header_height

        # ── 2. Holiday Warning Banner (Page 1 only) ──
        if holiday_info and page_num == 1:
            h_rect = [(40, current_y + 12), (width - 40, current_y + 98)]
            draw.rounded_rectangle(h_rect, radius=10, fill=(254, 242, 242), outline=(220, 38, 38), width=2)
            draw.text((65, current_y + 24), f"[TRADING HOLIDAY NOTICE] — {mkt} CLOSED / SPECIAL SESSION", fill=(185, 28, 28), font=self.font_bold)
            draw.text((65, current_y + 52), f"• Occasion: {clean_text_for_image(holiday_info.get('description', 'Market Holiday'))}", fill=(127, 29, 29), font=self.font_body)
            draw.text((600, current_y + 52), f"• Trading Session Status: {clean_text_for_image(holiday_info.get('trading_status', 'Closed'))}", fill=(153, 27, 27), font=self.font_bold)
            current_y += holiday_height

        # ── 3. High-Tech Statistics Ribbon (Strict Non-Overlapping Spacing) ──
        draw.rectangle([(0, current_y), (width, current_y + stats_ribbon_height)], fill=(248, 250, 252))
        draw.line([(0, current_y + stats_ribbon_height), (width, current_y + stats_ribbon_height)], fill=(226, 232, 240), width=1)

        # Col 1: Total Catalysts
        draw.text((45, current_y + 17), f"TOTAL CATALYSTS: {total_events_count}", fill=(15, 23, 42), font=self.font_bold)

        # Col 2: High Impact
        hi_color = (220, 38, 38) if high_impact_count > 0 else (71, 85, 105)
        draw.text((250, current_y + 17), f"HIGH-IMPACT: {high_impact_count}", fill=hi_color, font=self.font_bold)

        # Col 3: Status
        session_str = "HOLIDAY (CLOSED)" if holiday_info else "ACTIVE (REGULAR)"
        sess_color = (185, 28, 28) if holiday_info else (22, 101, 52)
        draw.text((450, current_y + 17), f"STATUS: {session_str}", fill=sess_color, font=self.font_bold)

        # Col 4: Page Indicator (or Wire Status)
        if total_pages > 1:
            draw.text((750, current_y + 17), f"PAGE {page_num} OF {total_pages} (ITEMS {start_idx}–{end_idx})", fill=(30, 58, 138), font=self.font_bold)
        else:
            draw.text((750, current_y + 17), "COMPLETE SCHEDULE", fill=(71, 85, 105), font=self.font_bold)

        # Col 5: Verified Wire
        draw.text((1040, current_y + 17), "VERIFIED WIRE", fill=theme["accent"], font=self.font_bold)

        current_y += stats_ribbon_height + 22

        # ── 4. Section Title ──
        section_txt = f"SCHEDULED ECONOMIC RELEASES & CORPORATE ACTIONS ({mkt})"
        if total_pages > 1:
            section_txt += f" — PART {page_num} OF {total_pages} (ITEMS {start_idx}–{end_idx} OF {total_events_count})"
        draw.text((45, current_y), section_txt, fill=(15, 23, 42), font=self.font_bold)
        draw.text((width - 320, current_y + 2), "Indian Standard Time (IST) Timings", fill=(100, 116, 139), font=self.font_small)
        current_y += 32

        # ── 5. Events List Cards ──
        if not page_events:
            empty_rect = [(40, current_y), (width - 40, current_y + 110)]
            draw.rounded_rectangle(empty_rect, radius=10, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
            draw.text((65, current_y + 38), f"• No official scheduled catalysts or corporate releases found for {mkt} on {date_formatted}.", fill=(100, 116, 139), font=self.font_bold)
            draw.text((65, current_y + 68), "• Regular secondary market liquidity and order books continue as scheduled.", fill=(148, 163, 184), font=self.font_body)
            current_y += 130
        else:
            for idx, e in enumerate(page_events, start=start_idx):
                is_high = str(e.get("impact", "")).upper() == "HIGH"
                card_bg = (255, 251, 235) if is_high else ((248, 250, 252) if (idx % 2 == 0) else (255, 255, 255))
                card_border = (251, 146, 60) if is_high else (226, 232, 240)
                border_width = 2 if is_high else 1

                row_h = event_row_height - 12
                row_rect = [(40, current_y), (width - 40, current_y + row_h)]
                draw.rounded_rectangle(row_rect, radius=8, fill=card_bg, outline=card_border, width=border_width)
                if is_high:
                    draw.rectangle([(40, current_y + 6), (46, current_y + row_h - 6)], fill=(234, 88, 12))

                # Time Badge (IST)
                time_str = f"{clean_text_for_image(e.get('time', '10:00'))} IST"
                time_badge_rect = [(54, current_y + 9), (175, current_y + 39)]
                t_bg = (220, 38, 38) if is_high else (15, 23, 42)
                draw.rounded_rectangle(time_badge_rect, radius=6, fill=t_bg)
                draw.text((64, current_y + 14), time_str, fill=(255, 255, 255), font=self.font_mono)

                # Impact Tag (Clean text, no emojis)
                imp_str = "HIGH IMPACT" if is_high else clean_text_for_image(e.get("impact", "MEDIUM"))
                imp_color = (194, 65, 12) if is_high else (71, 85, 105)
                draw.text((62, current_y + 47), imp_str, fill=imp_color, font=self.font_small)

                # Clean Symbol
                sym_str = clean_text_for_image(e.get("symbol", mkt))
                if ":" in sym_str:
                    clean_sym = sym_str.split(":", 1)[-1].strip()
                else:
                    clean_sym = sym_str

                # Clean Event Title (Safe width, truncated to max 60 chars)
                ev_str = clean_text_for_image(e.get("event", "Scheduled Release"))
                full_ev = f"{clean_sym} — {ev_str}"
                max_title_chars = 60
                if len(full_ev) > max_title_chars:
                    full_ev = full_ev[:max_title_chars - 3] + "..."

                draw.text((192, current_y + 11), full_ev, fill=(15, 23, 42), font=self.font_bold)

                # Financial Metrics: Prev vs Consensus vs Actual (Safe length, capped to max 65 chars)
                prev_val = (clean_text_for_image(e.get("previous", "—")) or "—")[:15]
                fore_val = (clean_text_for_image(e.get("forecast", "—")) or "—")[:18]
                act_val = (clean_text_for_image(e.get("actual", "Pending")) or "Pending")[:22]
                metrics_str = f"Prev: {prev_val}   |   Consensus: {fore_val}   |   Actual: {act_val}"
                draw.text((192, current_y + 44), metrics_str, fill=(71, 85, 105), font=self.font_body)

                # Verdict / Sentiment Pill (Drawn as dedicated high-contrast terminal pill)
                raw_sent = clean_text_for_image(e.get("outcome_sentiment", "PENDING")).upper()
                if "BULL" in raw_sent:
                    sent_str = "BULLISH"
                    pill_bg = (240, 253, 244)
                    pill_border = (187, 247, 208)
                    sent_color = (22, 101, 52)
                elif "BEAR" in raw_sent:
                    sent_str = "BEARISH"
                    pill_bg = (254, 242, 242)
                    pill_border = (254, 202, 202)
                    sent_color = (185, 28, 28)
                else:
                    sent_str = "PENDING"
                    pill_bg = (241, 245, 249)
                    pill_border = (226, 232, 240)
                    sent_color = (71, 85, 105)

                verdict_rect = [(width - 235, current_y + 20), (width - 55, current_y + 54)]
                draw.rounded_rectangle(verdict_rect, radius=6, fill=pill_bg, outline=pill_border, width=1)
                draw.text((width - 222, current_y + 27), f"VERDICT: {sent_str}", fill=sent_color, font=self.font_bold)

                current_y += event_row_height

        # ── 6. Pagination Navigation Banner ──
        if total_pages > 1:
            nav_rect = [(40, current_y), (width - 40, current_y + 42)]
            if page_num < total_pages:
                draw.rounded_rectangle(nav_rect, radius=6, fill=(239, 246, 255), outline=(191, 219, 254), width=1)
                remaining = total_events_count - end_idx
                draw.text((55, current_y + 12), f">> CONTINUED ON CARD {page_num + 1} OF {total_pages} (NEXT {remaining} EVENTS INCLUDED)", fill=(29, 78, 216), font=self.font_bold)
                draw.text((width - 360, current_y + 12), f"Part {page_num}/{total_pages} Dispatched to Telegram", fill=(100, 116, 139), font=self.font_small)
            else:
                draw.rounded_rectangle(nav_rect, radius=6, fill=(240, 253, 244), outline=(187, 247, 208), width=1)
                draw.text((55, current_y + 12), f"[ALL {total_events_count} {mkt} EVENTS DISPLAYED ACROSS {total_pages} CARDS]", fill=(22, 101, 52), font=self.font_bold)
                draw.text((width - 340, current_y + 12), "Complete Ledger Verified on EPM Pro", fill=(71, 85, 105), font=self.font_small)
            current_y += 54

        # ── 7. Futuristic Terminal Footer ──
        draw.line([(40, current_y + 8), (width - 40, current_y + 8)], fill=(226, 232, 240), width=1)
        dispatched_time = datetime.now().strftime("%d %b %Y, %H:%M:%S IST")
        draw.text((45, current_y + 18), f"EPM Pro Multi-Market Intelligence Engine  •  Verified Output at {dispatched_time}", fill=(148, 163, 184), font=self.font_small)
        draw.text((width - 420, current_y + 18), "• Synchronized with Google Calendar (60m Prior Alarms)", fill=(37, 99, 235), font=self.font_bold)

        # Mandatory Bottom Notifier / Disclaimer across very bottom
        draw.rectangle([(0, total_height - 34), (width, total_height)], fill=(15, 23, 42))
        draw.line([(0, total_height - 34), (width, total_height - 34)], fill=theme["accent"], width=2)
        disclaimer_text = "Global News Feed Room is Powered by EPMC Pvt. Ltd."
        d_bbox = draw.textbbox((0, 0), disclaimer_text, font=self.font_bold)
        d_w = d_bbox[2] - d_bbox[0]
        draw.text(((width - d_w) // 2, total_height - 26), disclaimer_text, fill=(241, 245, 249), font=self.font_bold)

        # Export to optimized PNG buffer
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue()

    def render_market_calendar_cards(
        self,
        market: str,
        target_date: str,
        events: List[Dict],
        mode: str = "TODAY",
        holiday_info: Optional[Dict] = None,
        max_per_page: int = 15
    ) -> List[Tuple[bytes, List[Dict], int, int]]:
        """
        Renders one or more publication-grade 1200px infographic cards.
        If events count exceeds max_per_page (e.g. 15), splits automatically into 2 or more cards
        so NO data is hidden with a "+X more events" message.
        Returns: List of tuples: (png_bytes, page_events, start_index, end_index)
        """
        sorted_events = sorted(
            events or [],
            key=lambda x: (0 if str(x.get("impact", "")).upper() == "HIGH" else 1, str(x.get("time", "99:99")))
        )

        total_count = len(sorted_events)
        high_impact_count = sum(1 for e in sorted_events if str(e.get("impact", "")).upper() == "HIGH")

        chunks = self.chunk_events_for_cards(sorted_events, max_per_page=max_per_page)
        total_pages = len(chunks)

        rendered_pages: List[Tuple[bytes, List[Dict], int, int]] = []
        for page_idx, (page_events, start_idx, end_idx) in enumerate(chunks, start=1):
            png_bytes = self.render_single_page(
                market=market,
                target_date=target_date,
                page_events=page_events,
                total_events_count=total_count,
                high_impact_count=high_impact_count,
                start_idx=start_idx,
                end_idx=end_idx,
                page_num=page_idx,
                total_pages=total_pages,
                mode=mode,
                holiday_info=holiday_info
            )
            rendered_pages.append((png_bytes, page_events, start_idx, end_idx))

        return rendered_pages

    def render_market_calendar_card(
        self,
        market: str,
        target_date: str,
        events: List[Dict],
        mode: str = "TODAY",
        holiday_info: Optional[Dict] = None
    ) -> bytes:
        """Single-card backward compatibility wrapper."""
        pages = self.render_market_calendar_cards(
            market=market,
            target_date=target_date,
            events=events,
            mode=mode,
            holiday_info=holiday_info,
            max_per_page=15
        )
        return pages[0][0] if pages else b""

calendar_card_generator = CalendarCardGenerator()
