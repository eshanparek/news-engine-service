import os
import io
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("NewsCardGenerator")

EMOJI_CLEAN_REGEX = re.compile(
    r"[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\u25b6\u25c0\ufe0f]+",
    flags=re.UNICODE
)

def clean_text_for_image(text: str) -> str:
    """Strips emoji codepoints and replaces unsupported currency symbols that cause tofu boxes."""
    if not text:
        return ""
    text = str(text).replace("₹", "Rs. ").replace("\u20b9", "Rs. ")
    cleaned = EMOJI_CLEAN_REGEX.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


class NewsCardGenerator:
    """
    Renders publication-grade 1080x1350 (4:5 portrait) financial news infographic cards.
    Designed for Instagram feed, Twitter media cards, Telegram photo alerts, and WhatsApp media.
    Inspired by Finshots, Inshorts, and Bloomberg Terminal styling.
    """
    def __init__(self):
        self._init_fonts()

    def _init_fonts(self):
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

        self.font_masthead = None
        self.font_headline = None
        self.font_section = None
        self.font_body = None
        self.font_bold = None
        self.font_tag = None
        self.font_footer = None

        for path in font_paths:
            if os.path.exists(path):
                try:
                    self.font_masthead = ImageFont.truetype(path, 22)
                    self.font_headline = ImageFont.truetype(path, 40)
                    self.font_section = ImageFont.truetype(path, 24)
                    self.font_body = ImageFont.truetype(path, 24)
                    self.font_bold = ImageFont.truetype(path, 25)
                    self.font_tag = ImageFont.truetype(path, 17)
                    self.font_footer = ImageFont.truetype(path, 15)
                    logger.info(f"Loaded TTF font for news cards: {path}")
                    break
                except Exception as e:
                    logger.warning(f"Failed loading font from {path}: {e}")
                    continue

        if not self.font_masthead:
            def_f = ImageFont.load_default()
            self.font_masthead = def_f
            self.font_headline = def_f
            self.font_section = def_f
            self.font_body = def_f
            self.font_bold = def_f
            self.font_tag = def_f
            self.font_footer = def_f

    def _wrap_text(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
        words = text.split()
        if not words:
            return []

        lines = []
        current_line = []

        for word in words:
            candidate = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), candidate, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    def render_news_card(self, news: Dict, width: int = 1080, height: int = 1350) -> bytes:
        """
        Renders a full 1080x1350 high-contrast infographic card and returns PNG bytes.
        """
        ai_score = int(news.get("ai_score", 5))
        ai_sentiment = str(news.get("ai_sentiment", "NEUTRAL")).upper()
        ai_impact = str(news.get("ai_impact", "MEDIUM")).upper()
        ai_reasoning = str(news.get("ai_reasoning", ""))
        ai_sectors = news.get("ai_sectors", [])
        title = clean_text_for_image(news.get("title", "Market Catalyst Update"))
        summary = clean_text_for_image(news.get("summary", ""))
        source = clean_text_for_image(news.get("source", "Market Wire"))
        timestamp = news.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M IST"))

        # Determine Color Accents by Sentiment / Impact
        is_high = (ai_score >= 8) or (ai_impact == "HIGH")
        if "BULL" in ai_sentiment:
            accent_color = (16, 185, 129)       # Neon Emerald Green
            accent_bg = (6, 78, 59)             # Deep Forest
            sentiment_text = "BULLISH CATALYST"
            sent_pill_bg = (16, 185, 129)
            sent_pill_text = (255, 255, 255)
        elif "BEAR" in ai_sentiment:
            accent_color = (239, 68, 68)        # Crimson Red
            accent_bg = (127, 29, 29)           # Deep Wine Red
            sentiment_text = "BEARISH CATALYST"
            sent_pill_bg = (239, 68, 68)
            sent_pill_text = (255, 255, 255)
        else:
            accent_color = (59, 130, 246)       # Electric Azure Blue
            accent_bg = (30, 58, 138)           # Navy Obsidian
            sentiment_text = "MARKET UPDATE"
            sent_pill_bg = (59, 130, 246)
            sent_pill_text = (255, 255, 255)

        # Base Image: Obsidian Dark Slate (#090d16)
        img = Image.new("RGB", (width, height), color=(9, 13, 22))
        draw = ImageDraw.Draw(img)

        # ── 1. Top Masthead Bar (0 to 110px) ──
        draw.rectangle([(0, 0), (width, 100)], fill=(15, 23, 42))
        # Accent Border Strip
        draw.rectangle([(0, 96), (width, 100)], fill=accent_color)

        # Brand Logo & Masthead
        draw.text((50, 34), "EPM PRO", fill=(255, 255, 255), font=self.font_headline)
        draw.text((230, 42), "INSTITUTIONAL FINANCIAL WIRE", fill=(148, 163, 184), font=self.font_masthead)

        # Clean Time Pill on Right
        clock_clean = clean_text_for_image(str(timestamp))
        if len(clock_clean) > 22:
            clock_clean = clock_clean[:22]
        time_rect = [(width - 320, 28), (width - 50, 72)]
        draw.rounded_rectangle(time_rect, radius=6, fill=(30, 41, 59), outline=(51, 65, 85), width=1)
        draw.text((width - 305, 38), f"LIVE WIRE | {clock_clean}", fill=(203, 213, 225), font=self.font_tag)

        # ── 2. Impact & Category Banner (120 to 190px) ──
        current_y = 130

        # Impact Badge
        score_badge = f"AI SCORE: {ai_score}/10"
        score_rect = [(50, current_y), (240, current_y + 44)]
        draw.rounded_rectangle(score_rect, radius=8, fill=(220, 38, 38) if is_high else (37, 99, 235))
        draw.text((68, current_y + 11), f"CRITICAL" if is_high else f"CATALYST", fill=(255, 255, 255), font=self.font_tag)
        draw.text((150, current_y + 11), f"| {ai_score}/10", fill=(255, 255, 255), font=self.font_tag)

        # Sentiment Pill
        sent_rect = [(255, current_y), (480, current_y + 44)]
        draw.rounded_rectangle(sent_rect, radius=8, fill=sent_pill_bg)
        draw.text((275, current_y + 11), sentiment_text, fill=sent_pill_text, font=self.font_tag)

        # Market Scope
        sectors_str = ", ".join(ai_sectors) if ai_sectors else "Macro Economy & Equities"
        clean_sectors = clean_text_for_image(sectors_str)[:45]
        sec_rect = [(495, current_y), (width - 50, current_y + 44)]
        draw.rounded_rectangle(sec_rect, radius=8, fill=(30, 41, 59), outline=(51, 65, 85), width=1)
        draw.text((515, current_y + 11), f"SCOPE: {clean_sectors.upper()}", fill=(226, 232, 240), font=self.font_tag)

        # ── 3. Main Breaking Headline (210 to 480px) ──
        current_y = 210

        headline_box_rect = [(50, current_y), (width - 50, current_y + 260)]
        draw.rounded_rectangle(headline_box_rect, radius=12, fill=(15, 23, 42), outline=(30, 41, 59), width=2)
        # Left Accent Border
        draw.rectangle([(50, current_y + 4), (58, current_y + 256)], fill=accent_color)

        headline_lines = self._wrap_text(draw, title, self.font_headline, max_width=920)
        # Display max 4 lines
        headline_y = current_y + 25
        for line in headline_lines[:4]:
            draw.text((80, headline_y), line, fill=(255, 255, 255), font=self.font_headline)
            headline_y += 52

        # ── 4. Institutional Takeaways / AI Analysis Box (500 to 1100px) ──
        current_y = 495
        takeaway_rect = [(50, current_y), (width - 50, current_y + 630)]
        draw.rounded_rectangle(takeaway_rect, radius=12, fill=(15, 23, 42), outline=(30, 41, 59), width=1)

        # Subheader banner inside takeaway box
        takeaway_hdr_rect = [(50, current_y), (width - 50, current_y + 60)]
        draw.rounded_rectangle(takeaway_hdr_rect, radius=12, fill=(30, 41, 59))
        draw.rectangle([(50, current_y + 56), (width - 50, current_y + 60)], fill=accent_color)
        draw.text((80, current_y + 16), "EXECUTIVE INTELLIGENCE & MARKET IMPACT", fill=(255, 255, 255), font=self.font_section)

        # Extract Key Bullet Points from AI reasoning / summary
        bullet_y = current_y + 85

        bullets = []
        if ai_reasoning:
            # Split AI reasoning into clean sentences or points
            sentences = [s.strip() for s in re.split(r"[.!?]\s+", ai_reasoning) if len(s.strip()) > 15]
            bullets.extend(sentences[:3])

        if len(bullets) < 2 and summary:
            summary_sentences = [s.strip() for s in re.split(r"[.!?]\s+", summary) if len(s.strip()) > 15]
            for s in summary_sentences:
                if s not in bullets and len(bullets) < 3:
                    bullets.append(s)

        if not bullets:
            bullets = [
                "Catalyst impact evaluated by EPM Pro multi-agent scoring model.",
                "Trading desks monitoring price action across key asset sectors.",
                "Institutional volume and volatility anticipated."
            ]

        for b_idx, bullet in enumerate(bullets[:3], 1):
            clean_b = clean_text_for_image(bullet)
            # Draw Bullet Index Badge
            badge_pos = [(80, bullet_y), (115, bullet_y + 35)]
            draw.rounded_rectangle(badge_pos, radius=6, fill=accent_bg, outline=accent_color, width=1)
            draw.text((93, bullet_y + 6), str(b_idx), fill=(255, 255, 255), font=self.font_bold)

            # Draw Wrapped Bullet Text
            b_lines = self._wrap_text(draw, clean_b, self.font_body, max_width=860)
            text_y = bullet_y + 4
            for line in b_lines[:3]:
                draw.text((135, text_y), line, fill=(226, 232, 240), font=self.font_body)
                text_y += 32

            bullet_y = max(bullet_y + 120, text_y + 35)

        # ── 5. Relevant Tickers & Cashtags Strip (1145 to 1210px) ──
        current_y = 1145
        tags = []
        if ai_sectors:
            tags.extend([f"#{clean_text_for_image(s).replace(' ', '').upper()}" for s in ai_sectors[:4]])
        tags.extend(["#NIFTY50", "#SENSEX", "#FINANCIALMARKETS", "#EPMWIRE"])

        tag_x = 50
        for tag in tags[:5]:
            tb = draw.textbbox((0, 0), tag, font=self.font_tag)
            tw = tb[2] - tb[0]
            tag_rect = [(tag_x, current_y), (tag_x + tw + 24, current_y + 38)]
            draw.rounded_rectangle(tag_rect, radius=6, fill=(30, 41, 59), outline=(71, 85, 105), width=1)
            draw.text((tag_x + 12, current_y + 10), tag, fill=(56, 189, 248), font=self.font_tag)
            tag_x += tw + 34
            if tag_x > width - 150:
                break

        # ── 6. Bottom Footer & Verification Strip (1240 to 1350px) ──
        draw.rectangle([(0, height - 90), (width, height)], fill=(15, 23, 42))
        draw.rectangle([(0, height - 90), (width, height - 88)], fill=(30, 41, 59))

        draw.text((50, height - 60), f"SOURCE: {source.upper()} | VERIFIED MARKET FEED", fill=(148, 163, 184), font=self.font_footer)
        draw.text((50, height - 38), "NOT INVESTMENT ADVICE | FOR INFORMATIONAL TRADING PURPOSES ONLY", fill=(100, 116, 139), font=self.font_footer)

        term_badge_rect = [(width - 340, height - 65), (width - 50, height - 25)]
        draw.rounded_rectangle(term_badge_rect, radius=6, fill=(2, 6, 23), outline=(37, 99, 235), width=1)
        draw.text((width - 325, height - 52), "POWERED BY EPM PRO TERMINAL", fill=(96, 165, 250), font=self.font_footer)

        # Output to PNG bytes
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True, dpi=(300, 300))
        return buffer.getvalue()


# Global Singleton
news_card_generator = NewsCardGenerator()
