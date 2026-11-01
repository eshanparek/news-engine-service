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
        # Progress segments (story-style)
        total = max(1, total)
        seg_gap = 10
        seg_w = (W - 2 * 48 - seg_gap * (total - 1)) / total
        for i in range(total):
            x0 = 48 + i * (seg_w + seg_gap)
            col = INK if i <= index else (203, 213, 225)
            d.rounded_rectangle([x0, 60, x0 + seg_w, 68], radius=4, fill=col)

        # Brand header
        d.text((pad, 110), "EPM", font=self._font(48), fill=INK)
        d.text((pad + d.textlength("EPM", font=self._font(48)), 110), "PRO", font=self._font(48), fill=BRAND_BLUE)
        kind_label = "MARKET CALENDAR" if item.get("kind") == "calendar" else "BREAKING WIRE"
        kf = self._font(26)
        kw = d.textlength(kind_label, font=kf)
        d.rounded_rectangle([W - pad - kw - 36, 112, W - pad, 160], radius=24, outline=(203, 213, 225), width=2, fill=(255, 255, 255))
        d.text((W - pad - kw - 18, 122), kind_label, font=kf, fill=MUTED)

        y = 360
        # Sentiment pill
        pf = self._font(38)
        label = key.title()
        pw = d.textlength(label, font=pf)
        px0 = (W - pw - 80) / 2
        d.rounded_rectangle([px0, y, px0 + pw + 80, y + 72], radius=36, fill=th["pill_bg"])
        d.ellipse([px0 + 26, y + 29, px0 + 40, y + 43], fill=th["accent"])
        d.text((px0 + 52, y + 14), label, font=pf, fill=th["pill_fg"])
        y += 110

        tag = clean_text_for_image(item.get("tag", "")).upper()
        if tag:
            tf = self._font(30)
            tw = d.textlength(tag, font=tf)
            d.text(((W - tw) / 2, y), tag, font=tf, fill=MUTED)
            y += 60

        # Headline (centered)
        title = clean_text_for_image(item.get("title", "Market Catalyst"))
        hf, lines = self._fit_headline(d, title, W - 2 * pad)
        lh = int(hf.size * 1.18)
        for ln in lines:
            lw = d.textlength(ln, font=hf)
            d.text(((W - lw) / 2, y), ln, font=hf, fill=INK)
            y += lh
        y += 40

        # Divider + two metrics
        d.line([pad, y, W - pad, y], fill=(226, 232, 240), width=3)
        y += 50
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
            d.text((cx - lw / 2, y + 130), ml, font=lf, fill=MUTED)
        d.line([W / 2, y + 10, W / 2, y + 160], fill=(226, 232, 240), width=3)
        y += 210
        d.line([pad, y, W - pad, y], fill=(226, 232, 240), width=3)
        y += 60

        # Bullets
        bf_bold = self._font(40)
        bf = self._font(38, bold=False)
        impact = clean_text_for_image(item.get("impact", ""))
        if impact:
            d.ellipse([pad, y + 16, pad + 14, y + 30], fill=INK)
            d.text((pad + 36, y), f"Impact: {impact}", font=bf_bold, fill=INK)
            y += 70
        for b in (item.get("bullets") or [])[:2]:
            b = clean_text_for_image(b)
            if not b:
                continue
            blines = self._wrap(d, b, bf, W - 2 * pad - 36, 4)
            d.ellipse([pad, y + 16, pad + 14, y + 30], fill=INK)
            for bl in blines:
                d.text((pad + 36, y), bl, font=bf, fill=MUTED)
                y += 54
            y += 20

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
        cta = "Live multi-market intelligence  |  EPMPRO"
        cw = d.textlength(cta, font=cf)
        d.text(((W - cw) / 2, H - 110), cta, font=cf, fill=FAINT)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


story_card_generator = StoryCardGenerator()
