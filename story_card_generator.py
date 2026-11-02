"""
Story Card Generator — renders 1080x1920 (9:16) Instagram Story flashcards.

One catalyst per frame (news item or calendar event), light/white theme with a
soft sentiment-tinted gradient, big two-metric block, impact + AI reasoning
bullets, and a segmented progress indicator so a sequence of frames reads like
a swipeable story when published back-to-back to an Instagram account.
"""
import io
import os
import logging
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from news_card_generator import clean_text_for_image

logger = logging.getLogger("StoryCardGenerator")

W, H = 1080, 1920

SENT_THEME = {
    "BULLISH": {"accent": (16, 185, 129), "tint": (209, 250, 229), "pill_bg": (220, 252, 231), "pill_fg": (4, 120, 87)},
    "BEARISH": {"accent": (244, 63, 94), "tint": (255, 228, 230), "pill_bg": (255, 228, 230), "pill_fg": (190, 18, 60)},
    "NEUTRAL": {"accent": (100, 116, 139), "tint": (226, 232, 240), "pill_bg": (241, 245, 249), "pill_fg": (51, 65, 85)},
}
INK = (15, 23, 42)
MUTED = (71, 85, 105)
FAINT = (148, 163, 184)
BRAND_BLUE = (0, 82, 255)


def _sent_key(sentiment: str) -> str:
    s = str(sentiment or "").upper()
    if "BULL" in s:
        return "BULLISH"
    if "BEAR" in s:
        return "BEARISH"
    return "NEUTRAL"


class StoryCardGenerator:
    def __init__(self):
        base = os.path.dirname(os.path.abspath(__file__))
        bold_candidates = [
            os.path.join(base, "assets", "fonts", "Arial Bold.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ]
        reg_candidates = [
            os.path.join(base, "assets", "fonts", "Arial.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
        self.bold_path = next((p for p in bold_candidates if os.path.exists(p)), None)
        self.reg_path = next((p for p in reg_candidates if os.path.exists(p)), self.bold_path)

    def _font(self, size: int, bold: bool = True):
        path = self.bold_path if bold else self.reg_path
        try:
            return ImageFont.truetype(path, size) if path else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    @staticmethod
    def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int, max_lines: int) -> List[str]:
        words = text.split()
        lines, cur = [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
                if len(lines) >= max_lines:
                    break
        if cur and len(lines) < max_lines:
            lines.append(cur)
        if len(lines) == max_lines and " ".join(lines) != text.strip():
            last = lines[-1]
            while last and draw.textlength(last + "…", font=font) > max_w:
                last = last[:-1]
            lines[-1] = last.rstrip() + "…"
        return lines

    def _fit_headline(self, draw, text: str, max_w: int) -> Tuple[object, List[str]]:
        for size in (96, 86, 76, 68, 60, 54):
            f = self._font(size)
            lines = self._wrap(draw, text, f, max_w, 4)
            if len(lines) <= 3 or size == 54:
                return f, lines
        f = self._font(54)
        return f, self._wrap(draw, text, f, max_w, 4)

    def render_story(self, item: Dict, index: int = 0, total: int = 1) -> bytes:
        """
        item keys: title, sentiment, kind ('news'|'calendar'), tag (e.g. 'MCX / COMMODITY'),
        metric1/metric1_label, metric2/metric2_label, impact, bullets (list[str]), source, time
        """
        key = _sent_key(item.get("sentiment"))
        th = SENT_THEME[key]

        img = Image.new("RGB", (W, H), (255, 255, 255))
        # Soft vertical gradient: sentiment tint at top fading to white
        grad = Image.new("RGB", (1, H))
        for y in range(H):
            t = min(1.0, y / (H * 0.62))
            r = int(th["tint"][0] * (1 - t) + 255 * t)
            g = int(th["tint"][1] * (1 - t) + 255 * t)
            b = int(th["tint"][2] * (1 - t) + 255 * t)
            grad.putpixel((0, y), (r, g, b))
        img.paste(grad.resize((W, H)))
        d = ImageDraw.Draw(img)

        pad = 84
        # Progress segments (story-style, clamped up to 30 for clean visual bar)
        total = max(1, total)
        display_total = min(total, 30)
        display_index = min(index, display_total - 1)
        seg_gap = 4 if display_total > 15 else 8
        available_w = max(100.0, W - 2 * 48 - seg_gap * (display_total - 1))
        seg_w = max(4.0, available_w / display_total)
        for i in range(display_total):
            x0 = 48 + i * (seg_w + seg_gap)
            col = INK if i <= display_index else (203, 213, 225)
            d.rounded_rectangle([x0, 60, x0 + seg_w, 68], radius=4, fill=col)

        # Brand header
        d.text((pad, 110), "GNC", font=self._font(48), fill=INK)
        k = item.get("kind")
        if k == "calendar":
            kind_label = "MARKET CALENDAR"
        elif k == "circulars":
            kind_label = "OFFICIAL CIRCULAR"
        elif k == "holidays":
            kind_label = "TRADING HOLIDAY"
        else:
            kind_label = "BREAKING WIRE"
        kf = self._font(26)
        kw = d.textlength(kind_label, font=kf)
        d.rounded_rectangle([W - pad - kw - 36, 112, W - pad, 160], radius=24, outline=(203, 213, 225), width=2, fill=(255, 255, 255))
        d.text((W - pad - kw - 18, 122), kind_label, font=kf, fill=MUTED)

        # Hero Image Banner (Web photo if available, or sector-specific vector graphic)
        banner_w = W - 2 * pad  # 912
        banner_h = 360
        hero_y = 175
        try:
            import image_assets
            t_img = None
            img_url = item.get("image_url") or item.get("image") or item.get("thumbnail")

            # 1. If it's a web URL, download the real story photo
            if img_url and str(img_url).startswith(("http://", "https://")):
                try:
                    import urllib.request
                    req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
                    with urllib.request.urlopen(req, timeout=3.0) as r:
                        raw_data = r.read()
                        if raw_data:
                            src_img = Image.open(io.BytesIO(raw_data)).convert("RGBA")
                            src_w, src_h = src_img.size
                            ratio = max(banner_w / max(1, src_w), banner_h / max(1, src_h))
                            new_size = (max(banner_w, int(src_w * ratio)), max(banner_h, int(src_h * ratio)))
                            resized = src_img.resize(new_size, Image.Resampling.LANCZOS)
                            left = max(0, (resized.width - banner_w) // 2)
                            top = max(0, (resized.height - banner_h) // 2)
                            t_img = resized.crop((left, top, left + banner_w, top + banner_h))
                except Exception as ex:
                    logger.debug(f"Failed to load web image {img_url}: {ex}")

            # 2. Vector fallback or regulatory/holiday/calendar art
            if t_img is None:
                t_bytes = None
                if k == "holidays":
                    t_bytes = image_assets.generate_holiday_thumb(item.get("date", ""), item.get("title", ""))
                elif k == "calendar":
                    t_bytes = image_assets.generate_calendar_thumb(
                        symbol=item.get("symbol", ""),
                        market=item.get("market", ""),
                        category=item.get("tag", ""),
                        title=item.get("title", "")
                    )
                elif k == "circulars":
                    t_bytes = image_assets.generate_regulator_logo(item.get("regulator", item.get("source", "NSE")))
                else:
                    t_bytes = image_assets.generate_news_thumb(
                        topic=item.get("tag", ""),
                        category=item.get("category", ""),
                        source=item.get("source", ""),
                        title=item.get("title", "")
                    )
                if t_bytes:
                    v_raw = Image.open(io.BytesIO(t_bytes)).convert("RGBA")
                    t_img = Image.new("RGBA", (banner_w, banner_h), (241, 245, 249, 255))
                    v_scaled = v_raw.resize((260, 260), Image.Resampling.LANCZOS)
                    t_img.paste(v_scaled, ((banner_w - 260) // 2, (banner_h - 260) // 2), v_scaled if v_scaled.mode == "RGBA" else None)

            if t_img:
                mask = Image.new("L", (banner_w, banner_h), 0)
                ImageDraw.Draw(mask).rounded_rectangle([0, 0, banner_w, banner_h], radius=24, fill=255)
                img.paste(t_img, (pad, hero_y), mask)
                d.rounded_rectangle([pad, hero_y, W - pad, hero_y + banner_h], radius=24, outline=(203, 213, 225), width=2)
        except Exception as e:
            logger.debug(f"Could not render hero banner: {e}")

        y = hero_y + banner_h + 30
        # Sentiment pill
        pf = self._font(38)
        label = key.title()
        pw = d.textlength(label, font=pf)
        px0 = (W - pw - 80) / 2
        d.rounded_rectangle([px0, y, px0 + pw + 80, y + 72], radius=36, fill=th["pill_bg"])
        d.ellipse([px0 + 26, y + 29, px0 + 40, y + 43], fill=th["accent"])
        d.text((px0 + 52, y + 14), label, font=pf, fill=th["pill_fg"])
        y += 100

        tag = clean_text_for_image(item.get("tag", "")).upper()
        if tag:
            tf = self._font(30)
            tw = d.textlength(tag, font=tf)
            d.text(((W - tw) / 2, y), tag, font=tf, fill=MUTED)
            y += 55

        # Headline (centered)
        title = clean_text_for_image(item.get("title", "Market Catalyst"))
        hf, lines = self._fit_headline(d, title, W - 2 * pad)
        lh = int(hf.size * 1.18)
        for ln in lines:
            lw = d.textlength(ln, font=hf)
            d.text(((W - lw) / 2, y), ln, font=hf, fill=INK)
            y += lh
        y += 35

        # Divider + two metrics
        d.line([pad, y, W - pad, y], fill=(226, 232, 240), width=3)
        y += 45
        m1, m1l = clean_text_for_image(str(item.get("metric1", "—"))), clean_text_for_image(item.get("metric1_label", ""))
        m2, m2l = clean_text_for_image(str(item.get("metric2", "—"))), clean_text_for_image(item.get("metric2_label", ""))
        col_w = (W - 2 * pad) / 2
        for ci, (mv, ml) in enumerate(((m1, m1l), (m2, m2l))):
            cx = pad + col_w * ci + col_w / 2
            for size in (110, 92, 76, 62, 50):
                mf = self._font(size)
                if d.textlength(mv, font=mf) <= col_w - 40:
                    break
            mw = d.textlength(mv, font=mf)
            d.text((cx - mw / 2, y), mv, font=mf, fill=th["accent"] if ci == 1 else INK)
            lf = self._font(30, bold=False)
            lw = d.textlength(ml, font=lf)
            d.text((cx - lw / 2, y + 120), ml, font=lf, fill=MUTED)
        d.line([W / 2, y + 10, W / 2, y + 150], fill=(226, 232, 240), width=3)
        y += 190
        d.line([pad, y, W - pad, y], fill=(226, 232, 240), width=3)
        y += 50

        # Bullets
        bf_bold = self._font(38)
        bf = self._font(36, bold=False)
        impact = clean_text_for_image(item.get("impact", ""))
        if impact:
            d.ellipse([pad, y + 14, pad + 14, y + 28], fill=INK)
            d.text((pad + 36, y), f"Impact: {impact}", font=bf_bold, fill=INK)
            y += 65
        for b in (item.get("bullets") or [])[:2]:
            b = clean_text_for_image(b)
            if not b:
                continue
            blines = self._wrap(d, b, bf, W - 2 * pad - 36, 3)
            d.ellipse([pad, y + 14, pad + 14, y + 28], fill=INK)
            for bl in blines:
                d.text((pad + 36, y), bl, font=bf, fill=MUTED)
                y += 50
            y += 15

        # Footer
        ff = self._font(28, bold=False)
        src = clean_text_for_image(" · ".join(x for x in [item.get("source", ""), item.get("time", "")] if x))
        if src:
            sw = d.textlength(src, font=ff)
            d.text(((W - sw) / 2, H - 230), src, font=ff, fill=FAINT)
        # Dots indicator
        n = min(total, 8)
        dot_y = H - 160
        step = 36
        start = W / 2 - (n * step) / 2
        for i in range(n):
            cx = start + i * step
            if i == min(index, n - 1):
                d.rounded_rectangle([cx, dot_y, cx + 28, dot_y + 12], radius=6, fill=INK)
            else:
                d.ellipse([cx + 8, dot_y, cx + 20, dot_y + 12], fill=(203, 213, 225))
        cf = self._font(26, bold=False)
        cta = "Live multi-market intelligence  |  GNC"
        cw = d.textlength(cta, font=cf)
        d.text(((W - cw) / 2, H - 110), cta, font=cf, fill=FAINT)

        # Tiny Regulatory Disclaimer wrapped to 2 clean lines
        disc_font = self._font(19, bold=False)
        disc_msg = "This document and information in this document is not an investment advise. The creator and publisher are not responsible for your actions; for knowledge and educational purpose only."
        disc_lines = self._wrap(d, disc_msg, disc_font, W - 140, 2)
        disc_y = H - 65
        for dline in disc_lines:
            dw = d.textlength(dline, font=disc_font)
            d.text(((W - dw) / 2, disc_y), dline, font=disc_font, fill=(148, 163, 184))
            disc_y += 24

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


story_card_generator = StoryCardGenerator()
