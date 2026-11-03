import io
import os
import re
import math
import html
import functools
from typing import List, Dict, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont


def _load_font(size: int, bold: bool = False):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


# ─────────────────────────────────────────────────────────────────────────────
# 1. SOCIAL SHARE & OPEN GRAPH BANNER (1200x630)
# ─────────────────────────────────────────────────────────────────────────────

def generate_og_image() -> bytes:
    """Renders a 1200x630 high-contrast OpenGraph preview image for social link sharing."""
    w, h = 1200, 630
    img = Image.new("RGB", (w, h), (15, 23, 42))  # Slate 900
    d = ImageDraw.Draw(img)

    # Top Royal Blue accent bar
    d.rectangle([0, 0, w, 8], fill=(0, 82, 255))

    # Clean White Card Surface
    pad = 48
    d.rounded_rectangle([pad, 40, w - pad, h - 40], radius=16, fill=(255, 255, 255), outline=(226, 232, 240), width=2)

    f_title = _load_font(52, bold=True)
    f_sub = _load_font(24, bold=False)
    f_tag = _load_font(18, bold=True)
    f_feat_t = _load_font(20, bold=True)
    f_feat_d = _load_font(16, bold=False)
    f_disc = _load_font(15, bold=False)

    # Top badge pill: INSTITUTIONAL TERMINAL
    d.rounded_rectangle([pad + 36, 75, pad + 270, 112], radius=6, fill=(239, 246, 255), outline=(191, 219, 254), width=1)
    d.text((pad + 48, 82), "INSTITUTIONAL TERMINAL", font=f_tag, fill=(0, 82, 255))

    # Live Badge
    d.rounded_rectangle([pad + 285, 75, pad + 415, 112], radius=6, fill=(254, 242, 242), outline=(254, 202, 202), width=1)
    d.text((pad + 298, 82), "● LIVE STREAM", font=f_tag, fill=(220, 38, 38))

    # Main Brand Title
    d.text((pad + 36, 130), "Global News and Calender", font=f_title, fill=(15, 23, 42))

    # Subtitle
    d.text((pad + 36, 200), "Real-Time Multi-Market Intelligence, Catalyst Dossiers & Regulatory Wire", font=f_sub, fill=(100, 116, 139))

    # Horizontal divider
    d.line([pad + 36, 245, w - pad - 36, 245], fill=(226, 232, 240), width=2)

    # 3 Feature Bento Cards
    b_y = 270
    b_h = 220
    bw = (w - 2 * pad - 72 - 36) // 3
    features = [
        ("⚡ LIVE BREAKING WIRE", "NSE, BSE, MCX, Reuters, Bloomberg, SEBI & RBI streams scored by Gemini 2.5 AI.", (240, 253, 250), (13, 148, 136)),
        ("📅 5-MARKET CALENDAR", "Chronological timers, outcome trackers & automated 5 PM / Weekly / Monthly dossiers.", (239, 246, 255), (0, 82, 255)),
        ("🏛️ STATUTORY CIRCULARS", "Official compliance repository, directives, and instant verified PDF downloads.", (254, 243, 199), (217, 119, 6))
    ]

    for fi, (ft, fd, fbg, ffg) in enumerate(features):
        bx = pad + 36 + fi * (bw + 18)
        d.rounded_rectangle([bx, b_y, bx + bw, b_y + b_h], radius=12, fill=fbg, outline=(226, 232, 240), width=1)
        d.text((bx + 18, b_y + 18), ft, font=f_feat_t, fill=ffg)
        
        words = fd.split()
        l1 = " ".join(words[:5])
        l2 = " ".join(words[5:10])
        l3 = " ".join(words[10:])
        d.text((bx + 18, b_y + 60), l1, font=f_feat_d, fill=(51, 65, 85))
        d.text((bx + 18, b_y + 90), l2, font=f_feat_d, fill=(51, 65, 85))
        if l3:
            d.text((bx + 18, b_y + 120), l3, font=f_feat_d, fill=(51, 65, 85))

    # Footer Disclaimer
    disc = "This site is for Educational and knowledge purpose only, and not an Investment advice. We are not responsible for actions or loss."
    d.text((pad + 36, h - 85), disc, font=f_disc, fill=(148, 163, 184))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 2. FULL-SCHEDULE TRADING HOLIDAYS POSTER (1200x1550)
# ─────────────────────────────────────────────────────────────────────────────

def generate_holidays_image(holidays: List[Dict]) -> bytes:
    """Renders a publication-grade, high-resolution PNG image of the 2026 trading holidays for instant download."""
    w, h = 1200, 1550
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)

    f_h1 = _load_font(34, bold=True)
    f_sub = _load_font(18, bold=False)
    f_bold = _load_font(20, bold=True)
    f_body = _load_font(18, bold=False)
    f_pill = _load_font(15, bold=True)
    f_disc = _load_font(14, bold=False)

    # Top Brand Header (Royal Blue #0052FF)
    d.rectangle([0, 0, w, 110], fill=(0, 82, 255))
    d.text((48, 22), "GLOBAL NEWS AND CALENDER  |  GNC", font=f_h1, fill=(255, 255, 255))
    d.text((48, 68), "2026 AUTHORITATIVE TRADING HOLIDAYS & CLOSURES SCHEDULE", font=f_sub, fill=(203, 213, 225))

    # Table Header Row
    y = 130
    d.rectangle([48, y, w - 48, y + 42], fill=(241, 245, 249))
    d.text((62, y + 10), "DATE & DAY", font=f_bold, fill=(71, 85, 105))
    d.text((310, y + 10), "HOLIDAY OCCASION", font=f_bold, fill=(71, 85, 105))
    d.text((680, y + 10), "INDIAN EXCHANGES (NSE/BSE)", font=f_bold, fill=(71, 85, 105))
    d.text((960, y + 10), "MCX COMMODITY", font=f_bold, fill=(71, 85, 105))
    y += 50

    for idx, h_item in enumerate(holidays[:23]):
        row_bg = (255, 255, 255) if idx % 2 == 0 else (248, 250, 252)
        d.rectangle([48, y, w - 48, y + 48], fill=row_bg)

        d_str = f"{h_item.get('date', '')} ({h_item.get('day', '')[:3]})"
        desc = str(h_item.get('description', 'Market Holiday'))[:34]
        nse_st = str(h_item.get('nse_status', 'Closed'))
        mcx_st = str(h_item.get('mcx_status', 'Closed'))

        if "MORN: CLOSED" in mcx_st:
            mcx_disp = "Eve Open (17:00)"
        elif "FULL" in mcx_st.upper():
            mcx_disp = "Full Closed"
        else:
            mcx_disp = "Open"

        d.text((62, y + 13), d_str, font=f_bold, fill=(15, 23, 42))
        d.text((310, y + 13), desc, font=f_body, fill=(30, 41, 59))

        # NSE/BSE Status Pill
        is_closed = "Closed" in nse_st
        p_bg = (254, 242, 242) if is_closed else (240, 253, 250)
        p_fg = (220, 38, 38) if is_closed else (13, 148, 136)
        d.rounded_rectangle([680, y + 7, 860, y + 41], radius=6, fill=p_bg)
        d.text((695, y + 13), "CLOSED" if is_closed else "OPEN", font=f_pill, fill=p_fg)

        # MCX Status Pill
        mcx_closed = "Closed" in mcx_disp
        m_bg = (254, 243, 199) if "Eve" in mcx_disp else ((254, 242, 242) if mcx_closed else (240, 253, 250))
        m_fg = (180, 83, 9) if "Eve" in mcx_disp else ((220, 38, 38) if mcx_closed else (13, 148, 136))
        d.rounded_rectangle([960, y + 7, 1130, y + 41], radius=6, fill=m_bg)
        d.text((975, y + 13), mcx_disp.upper(), font=f_pill, fill=m_fg)

        d.line([48, y + 48, w - 48, y + 48], fill=(226, 232, 240), width=1)
        y += 50

    # Bottom Statutory Disclaimer Box
    d.rectangle([48, h - 85, w - 48, h - 25], fill=(248, 250, 252), outline=(226, 232, 240), width=1)
    disc_text = "This document is for Educational and knowledge purpose only, and not an Investment advice. We are not responsible for actions or loss."
    d.text((68, h - 60), disc_text, font=f_disc, fill=(100, 116, 139))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 3. FESTIVE & SEASONAL HOLIDAY PICTURES (240x240)
# ─────────────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=128)
def generate_holiday_thumb(holiday_key: str, title: str = "") -> bytes:
    """Renders high-quality, illustrative festival pictures (e.g. Christmas tree, Diwali diya, Tricolor, Holi colors)."""
    w, h = 240, 240
    key_norm = (holiday_key + " " + title).lower()
    
    img = Image.new("RGB", (w, h), (15, 23, 42))
    d = ImageDraw.Draw(img)

    f_sub = _load_font(13, bold=True)
    f_lg = _load_font(16, bold=True)

    # 1. CHRISTMAS (25 Dec)
    if any(k in key_norm for k in ["christmas", "xmas", "12-25"]):
        # Midnight snowy sky
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Snowy ground
        d.chord([0, 170, w, 280], start=180, end=360, fill=(241, 245, 249))
        # Brown Trunk
        d.rectangle([108, 170, 132, 205], fill=(120, 53, 15))
        # 3-Tier Pine Tree
        d.polygon([(120, 45), (65, 105), (175, 105)], fill=(22, 101, 52))
        d.polygon([(120, 80), (45, 145), (195, 145)], fill=(21, 128, 61))
        d.polygon([(120, 115), (30, 185), (210, 185)], fill=(34, 197, 94))
        # Golden glowing top star
        cx, cy, r = 120, 42, 14
        star_pts = []
        for i in range(10):
            rad = r if i % 2 == 0 else r * 0.45
            ang = math.radians(i * 36 - 90)
            star_pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        d.polygon(star_pts, fill=(250, 204, 21))
        # Bauble ornaments
        for ox, oy, col in [(85, 130, (239, 68, 68)), (155, 130, (250, 204, 21)), (120, 100, (59, 130, 246)), (75, 170, (244, 63, 94)), (165, 170, (239, 68, 68)), (120, 155, (250, 204, 21))]:
            d.ellipse([ox - 5, oy - 5, ox + 5, oy + 5], fill=col)
        # Snowflakes
        for sx, sy in [(30, 40), (210, 50), (40, 110), (200, 100), (25, 160), (215, 160)]:
            d.ellipse([sx - 2, sy - 2, sx + 2, sy + 2], fill=(255, 255, 255))
        lbl = "CHRISTMAS 2026"

    # 2. DIWALI / LAXMI PUJAN (Nov)
    elif any(k in key_norm for k in ["diwali", "deepawali", "laxmi", "balipratipada", "11-08", "11-10"]):
        # Royal deep purple-indigo background
        img.paste((46, 16, 101), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Decorative Rangoli arcs
        for r_arc in [80, 105, 130]:
            d.arc([120 - r_arc, 160 - r_arc, 120 + r_arc, 160 + r_arc], start=0, end=360, fill=(109, 40, 217), width=1)
        # Terracotta Diya body
        d.chord([45, 120, 195, 205], start=0, end=180, fill=(217, 119, 6), outline=(245, 158, 11), width=3)
        # Diya rim pattern
        for bx in range(55, 190, 15):
            d.ellipse([bx - 3, 125, bx + 3, 131], fill=(254, 240, 138))
        # Radiant Flame Halo
        d.ellipse([95, 45, 145, 130], fill=(245, 158, 11, 80))
        # Golden Flame
        d.ellipse([105, 55, 135, 125], fill=(245, 158, 11))
        d.ellipse([112, 70, 128, 115], fill=(254, 240, 138))
        # Sparklers
        for spk_x, spk_y in [(40, 60), (200, 60), (30, 100), (210, 100)]:
            d.line([spk_x - 8, spk_y, spk_x + 8, spk_y], fill=(250, 204, 21), width=2)
            d.line([spk_x, spk_y - 8, spk_x, spk_y + 8], fill=(250, 204, 21), width=2)
        lbl = "SHUBH DEEPAWALI"

    # 3. REPUBLIC DAY & INDEPENDENCE DAY (26 Jan, 15 Aug)
    elif any(k in key_norm for k in ["republic", "independence", "01-26", "08-15"]):
        # Indian National Flag Tricolor Canvas
        d.rectangle([0, 0, w, 80], fill=(255, 153, 51))    # Saffron
        d.rectangle([0, 80, w, 160], fill=(255, 255, 255))  # White
        d.rectangle([0, 160, w, 240], fill=(19, 136, 8))   # Green
        # Ashok Chakra (Navy Blue ring and 24 spokes)
        cx, cy, r_c = 120, 120, 32
        d.ellipse([cx - r_c, cy - r_c, cx + r_c, cy + r_c], outline=(0, 0, 128), width=3)
        d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(0, 0, 128))
        for i in range(24):
            ang = math.radians(i * (360 / 24))
            x2 = cx + r_c * math.cos(ang)
            y2 = cy + r_c * math.sin(ang)
            d.line([cx, cy, x2, y2], fill=(0, 0, 128), width=2)
        lbl = "REPUBLIC DAY 🇮🇳" if "republic" in key_norm else "INDEPENDENCE DAY 🇮🇳"

    # 4. HOLI (March)
    elif any(k in key_norm for k in ["holi", "03-03", "03-04"]):
        # Warm festive background
        img.paste((255, 247, 237), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Splashes of vibrant gulal colors
        for sp_x, sp_y, sp_r, col in [
            (50, 60, 40, (219, 39, 119)),   # Magenta
            (190, 70, 45, (14, 165, 233)),   # Cyan
            (120, 50, 35, (234, 179, 8)),    # Yellow
            (40, 170, 30, (168, 85, 247)),   # Purple
            (200, 160, 35, (34, 197, 94))    # Green
        ]:
            d.ellipse([sp_x - sp_r, sp_y - sp_r, sp_x + sp_r, sp_y + sp_r], fill=col)
        # 3 Traditional brass color bowls (Gulal Thaals)
        d.chord([30, 120, 100, 190], start=0, end=180, fill=(219, 39, 119), outline=(157, 23, 77), width=3)
        d.chord([85, 100, 155, 170], start=0, end=180, fill=(14, 165, 233), outline=(3, 105, 161), width=3)
        d.chord([140, 120, 210, 190], start=0, end=180, fill=(234, 179, 8), outline=(161, 98, 7), width=3)
        lbl = "HOLI FESTIVAL"

    # 5. SHRI RAM NAVAMI & DUSSEHRA
    elif any(k in key_norm for k in ["ram navami", "dussehra", "03-26", "10-20"]):
        # Radiant Saffron Dawn
        img.paste((255, 247, 237), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Sunburst rays
        cx, cy = 120, 120
        d.ellipse([cx - 50, cy - 50, cx + 50, cy + 50], fill=(254, 215, 170))
        d.ellipse([cx - 35, cy - 35, cx + 35, cy + 35], fill=(251, 146, 60))
        # Golden Bow arc & Blazing Arrow
        d.arc([50, 60, 150, 180], start=270, end=90, fill=(194, 65, 12), width=5)
        d.line([100, 60, 100, 180], fill=(120, 53, 15), width=2)
        d.line([60, 120, 180, 120], fill=(217, 119, 6), width=4)
        d.polygon([(180, 120), (160, 110), (160, 130)], fill=(234, 88, 12))
        lbl = "SHRI RAM NAVAMI" if "ram" in key_norm else "VIJAYA DASHAMI"

    # 6. EID-UL-FITR & BAKRI ID (EID-UL-ADHA) & MUHARRAM
    elif any(k in key_norm for k in ["eid", "bakri", "id-ul", "muharram", "05-28", "06-26"]):
        # Islamic Emerald Green Background
        img.paste((6, 78, 59), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Golden Crescent Moon
        d.ellipse([50, 45, 175, 175], fill=(250, 204, 21))
        d.ellipse([80, 40, 195, 165], fill=(6, 78, 59))
        # 5-Pointed Star
        cx, cy, r_s = 155, 95, 16
        star_pts = []
        for i in range(10):
            rad = r_s if i % 2 == 0 else r_s * 0.45
            ang = math.radians(i * 36 - 90)
            star_pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
        d.polygon(star_pts, fill=(250, 204, 21))
        # Mosque Minaret Dome Silhouette
        d.polygon([(100, 210), (120, 180), (140, 210)], fill=(4, 47, 46))
        d.rectangle([110, 200, 130, 240], fill=(4, 47, 46))
        lbl = "EID MUBARAK" if "eid" in key_norm or "bakri" in key_norm else "MUHARRAM"

    # 7. GOOD FRIDAY & EASTER (April)
    elif any(k in key_norm for k in ["good friday", "easter", "04-03"]):
        # Dawn Horizon Sky
        img.paste((30, 41, 59), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Sunburst dawn behind cross
        for i in range(12):
            ang = math.radians(i * 30)
            x_ray = 120 + 80 * math.cos(ang)
            y_ray = 100 + 80 * math.sin(ang)
            d.line([120, 100, x_ray, y_ray], fill=(148, 163, 184), width=1)
        # Golden Cross
        d.rounded_rectangle([108, 35, 132, 190], radius=4, fill=(245, 158, 11), outline=(254, 240, 138), width=2)
        d.rounded_rectangle([65, 75, 175, 105], radius=4, fill=(245, 158, 11), outline=(254, 240, 138), width=2)
        lbl = "GOOD FRIDAY"

    # 8. MAHATMA GANDHI JAYANTI (02 Oct)
    elif any(k in key_norm for k in ["gandhi", "10-02"]):
        img.paste((248, 250, 252), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Gandhi iconic round spectacles
        d.ellipse([45, 90, 110, 155], outline=(15, 23, 42), width=4)
        d.ellipse([130, 90, 195, 155], outline=(15, 23, 42), width=4)
        d.line([110, 115, 130, 115], fill=(15, 23, 42), width=4)
        # Spinning charkha wheel representation
        d.ellipse([90, 30, 150, 90], outline=(100, 116, 139), width=2)
        for i in range(8):
            ang = math.radians(i * 45)
            d.line([120, 60, 120 + 28 * math.cos(ang), 60 + 28 * math.sin(ang)], fill=(100, 116, 139), width=1)
        lbl = "GANDHI JAYANTI"

    # 9. GURU NANAK JAYANTI (24 Nov)
    elif any(k in key_norm for k in ["guru nanak", "gurpurb", "11-24"]):
        img.paste((23, 37, 84), [0, 0, w, h])  # Blue 950
        d = ImageDraw.Draw(img)
        # Glowing Golden Dome / Ik Onkar radiance
        d.ellipse([70, 70, 170, 170], fill=(254, 240, 138))
        d.ellipse([80, 80, 160, 160], fill=(245, 158, 11))
        # Golden Temple silhouette
        d.rectangle([90, 150, 150, 190], fill=(250, 204, 21))
        d.polygon([(90, 150), (120, 120), (150, 150)], fill=(250, 204, 21))
        lbl = "GURU NANAK JAYANTI"

    # 10. NEW YEAR'S DAY (01 Jan)
    elif any(k in key_norm for k in ["new year", "01-01"]):
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Midnight celebration clock & fireworks
        d.ellipse([60, 50, 180, 170], outline=(250, 204, 21), width=4)
        d.line([120, 110, 120, 65], fill=(255, 255, 255), width=3)  # 12 o'clock hour hand
        d.line([120, 110, 120, 55], fill=(239, 68, 68), width=2)    # Minute hand
        d.ellipse([115, 105, 125, 115], fill=(250, 204, 21))
        lbl = "NEW YEAR 2026 🎆"

    # 11. THANKSGIVING DAY (US - Nov)
    elif any(k in key_norm for k in ["thanksgiving", "11-26"]):
        img.paste((124, 45, 18), [0, 0, w, h])  # Autumn Amber
        d = ImageDraw.Draw(img)
        # Autumn Pumpkin
        d.ellipse([65, 80, 175, 180], fill=(234, 88, 12))
        d.ellipse([85, 80, 155, 180], fill=(249, 115, 22))
        d.ellipse([100, 80, 140, 180], fill=(251, 146, 60))
        # Stem
        d.rectangle([114, 60, 126, 85], fill=(69, 26, 3))
        lbl = "THANKSGIVING (US)"

    # DEFAULT / OTHER HOLIDAYS (Elections, Maharashtra Day, Ambedkar Jayanti, etc.)
    else:
        img.paste((241, 245, 249), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Calendar page motif
        d.rounded_rectangle([35, 35, 205, 205], radius=12, fill=(255, 255, 255), outline=(203, 213, 225), width=2)
        d.rounded_rectangle([35, 35, 205, 75], radius=10, fill=(0, 82, 255))
        d.ellipse([70, 48, 82, 60], fill=(255, 255, 255))
        d.ellipse([158, 48, 170, 60], fill=(255, 255, 255))
        d.text((82, 100), "2026", font=_load_font(28, bold=True), fill=(15, 23, 42))
        lbl = (title or "TRADING HOLIDAY")[:18].upper()

    # Bottom Pill Overlay Banner
    d.rounded_rectangle([15, h - 38, w - 15, h - 10], radius=6, fill=(15, 23, 42, 230), outline=(255, 255, 255, 60), width=1)
    tw = d.textlength(lbl, font=f_sub)
    d.text(((w - tw) / 2, h - 33), lbl, font=f_sub, fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 4. OFFICIAL REGULATOR & EXCHANGE LOGOS (240x240)
# ─────────────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=128)
def generate_regulator_logo(reg_code: str) -> bytes:
    """Renders authoritative, pixel-perfect official logos for financial authorities (SEBI, RBI, NSE, BSE, MCX, SEC, FED)."""
    w, h = 240, 240
    code = (reg_code or "").upper().strip()

    # 0. Check authentic uploaded logo repository first (User Verified Logos)
    logos_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logos")
    code_map = {
        "RBI": "rbi.png",
        "MCX": "mcx.png",
        "NYSE": "nyse.png",
        "FOMC": "fomc.png",
        "FED": "fomc.png",
        "US_GOVT": "us_govt.png",
        "GOVT": "us_govt.png",
        "WHITE HOUSE": "us_govt.png",
        "POTUS": "us_govt.png"
    }
    for k, fn in code_map.items():
        if k in code:
            fp = os.path.join(logos_dir, fn)
            if os.path.exists(fp):
                try:
                    src = Image.open(fp).convert("RGBA")
                    max_w, max_h = 210, 210
                    src.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                    canvas = Image.new("RGBA", (w, h), (255, 255, 255, 0))
                    paste_x = (w - src.width) // 2
                    paste_y = (h - src.height) // 2
                    canvas.paste(src, (paste_x, paste_y), src)
                    buf = io.BytesIO()
                    canvas.save(buf, format="PNG")
                    return buf.getvalue()
                except Exception as ex:
                    logger.debug(f"Failed loading authentic logo {fp}: {ex}")

    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)

    f_title = _load_font(28, bold=True)
    f_sub = _load_font(13, bold=True)

    # 1. SEBI (Securities and Exchange Board of India)
    if "SEBI" in code:
        img.paste((239, 246, 255), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Royal Blue Shield
        d.polygon([(120, 25), (195, 55), (195, 140), (120, 195), (45, 140), (45, 55)], fill=(0, 82, 255), outline=(217, 119, 6), width=3)
        # Golden inner emblem & Lion motif representation
        d.ellipse([100, 75, 140, 115], fill=(250, 204, 21))
        d.text((68, 130), "SEBI", font=f_title, fill=(255, 255, 255))
        d.text((38, 208), "SECURITIES REGULATOR", font=f_sub, fill=(0, 82, 255))

    # 2. RBI (Reserve Bank of India)
    elif "RBI" in code:
        img.paste((240, 253, 250), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Circular Royal Seal
        cx, cy, r_r = 120, 110, 85
        d.ellipse([cx - r_r, cy - r_r, cx + r_r, cy + r_r], fill=(13, 148, 136), outline=(250, 204, 21), width=4)
        d.ellipse([cx - r_r + 8, cy - r_r + 8, cx + r_r - 8, cy + r_r - 8], outline=(255, 255, 255), width=2)
        # Golden Palm tree & Tiger representation
        d.ellipse([110, 50, 130, 85], fill=(250, 204, 21))
        d.rectangle([116, 75, 124, 125], fill=(250, 204, 21))
        d.rounded_rectangle([85, 125, 155, 150], radius=8, fill=(250, 204, 21))
        d.text((82, 160), "RBI", font=_load_font(26, bold=True), fill=(255, 255, 255))
        d.text((45, 208), "CENTRAL BANK OF INDIA", font=f_sub, fill=(13, 148, 136))

    # 3. NSE (National Stock Exchange)
    elif "NSE" in code:
        img.paste((255, 255, 255), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Dynamic Interlocking Orange & Navy Bands
        cx, cy, r_n = 120, 105, 75
        d.ellipse([cx - r_n, cy - r_n, cx + r_n, cy + r_n], outline=(234, 88, 12), width=14)
        d.arc([cx - r_n + 12, cy - r_n + 12, cx + r_n - 12, cy + r_n - 12], start=45, end=240, fill=(30, 58, 138), width=12)
        d.text((75, 88), "NSE", font=_load_font(36, bold=True), fill=(30, 58, 138))
        d.text((36, 208), "NATIONAL STOCK EXCHANGE", font=f_sub, fill=(234, 88, 12))

    # 4. BSE (Bombay Stock Exchange)
    elif "BSE" in code:
        img.paste((239, 246, 255), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Phiroze Jeejeebhoy Towers silhouette & Bull Emblem
        d.rectangle([95, 45, 145, 150], fill=(29, 78, 216))
        d.polygon([(95, 45), (120, 20), (145, 45)], fill=(29, 78, 216))
        d.text((78, 85), "BSE", font=_load_font(34, bold=True), fill=(255, 255, 255))
        # Base
        d.rounded_rectangle([60, 150, 180, 175], radius=6, fill=(217, 119, 6))
        d.text((44, 208), "BOMBAY STOCK EXCHANGE", font=f_sub, fill=(29, 78, 216))

    # 5. MCX (Multi Commodity Exchange)
    elif "MCX" in code or "COMMODITY" in code:
        img.paste((255, 251, 235), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Golden Hexagonal Diamond
        pts = [(120, 25), (190, 65), (190, 145), (120, 185), (50, 145), (50, 65)]
        d.polygon(pts, fill=(217, 119, 6), outline=(245, 158, 11), width=4)
        d.text((72, 85), "MCX", font=_load_font(36, bold=True), fill=(255, 255, 255))
        d.text((46, 208), "COMMODITY DERIVATIVES", font=f_sub, fill=(217, 119, 6))

    # 6. US FED / FOMC
    elif "FED" in code or "FOMC" in code:
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        cx, cy, r_f = 120, 105, 80
        d.ellipse([cx - r_f, cy - r_f, cx + r_f, cy + r_f], fill=(30, 41, 59), outline=(250, 204, 21), width=3)
        # Eagle & Stars representation
        d.polygon([(120, 45), (160, 95), (80, 95)], fill=(250, 204, 21))
        d.rectangle([110, 90, 130, 135], fill=(250, 204, 21))
        d.text((68, 140), "FEDERAL", font=_load_font(18, bold=True), fill=(255, 255, 255))
        d.text((74, 160), "RESERVE", font=_load_font(18, bold=True), fill=(255, 255, 255))
        d.text((58, 208), "US CENTRAL BANK", font=f_sub, fill=(250, 204, 21))

    # 7. SEC (US Securities and Exchange Commission)
    elif "SEC" in code:
        img.paste((24, 39, 75), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        cx, cy, r_s = 120, 105, 80
        d.ellipse([cx - r_s, cy - r_s, cx + r_s, cy + r_s], fill=(30, 58, 138), outline=(250, 204, 21), width=3)
        d.text((75, 85), "SEC", font=_load_font(38, bold=True), fill=(255, 255, 255))
        d.text((45, 208), "US SECURITIES & EXCHANGE", font=f_sub, fill=(191, 219, 254))

    # 8. WHO (World Health Organization)
    elif "WHO" in code or "HEALTH" in code:
        img.paste((240, 249, 255), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        cx, cy, r_w = 120, 105, 78
        d.ellipse([cx - r_w, cy - r_w, cx + r_w, cy + r_w], fill=(2, 132, 199), outline=(186, 230, 253), width=4)
        # Globe grid lines
        d.ellipse([cx - 50, cy - 70, cx + 50, cy + 70], outline=(255, 255, 255), width=2)
        d.line([cx - 75, cy, cx + 75, cy], fill=(255, 255, 255), width=2)
        # Rod of Asclepius staff representation
        d.line([cx, cy - 55, cx, cy + 55], fill=(250, 204, 21), width=4)
        d.text((72, 85), "WHO", font=_load_font(36, bold=True), fill=(255, 255, 255))
        d.text((40, 208), "WORLD HEALTH ORG", font=f_sub, fill=(2, 132, 199))

    # 9. NYSE (New York Stock Exchange)
    elif "NYSE" in code or "WALL STREET" in code:
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Classical 11 Wall Street Facade & Pediment
        d.polygon([(120, 35), (195, 70), (45, 70)], fill=(217, 119, 6), outline=(250, 204, 21), width=2)
        # Pillars
        for px in [60, 85, 110, 135, 160]:
            d.rectangle([px, 75, px + 12, 150], fill=(255, 255, 255))
        d.rectangle([45, 150, 195, 165], fill=(217, 119, 6))
        d.text((68, 170), "NYSE", font=_load_font(28, bold=True), fill=(250, 204, 21))
        d.text((44, 208), "NEW YORK STOCK EXCHANGE", font=_load_font(12, bold=True), fill=(203, 213, 225))

    # 10. NASDAQ
    elif "NASDAQ" in code:
        img.paste((8, 145, 178), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        cx, cy, r_q = 120, 100, 72
        d.ellipse([cx - r_q, cy - r_q, cx + r_q, cy + r_q], outline=(255, 255, 255), width=10)
        # Q slant slash
        d.polygon([(155, 135), (185, 170), (170, 175), (145, 145)], fill=(255, 255, 255))
        d.text((50, 80), "Nasdaq", font=_load_font(32, bold=True), fill=(255, 255, 255))
        d.text((46, 208), "TECH SECURITIES EXCHANGE", font=_load_font(12, bold=True), fill=(255, 255, 255))

    # 11. DOW JONES
    elif "DOW" in code or "DJIA" in code:
        img.paste((220, 38, 38), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([35, 40, 205, 175], radius=16, fill=(255, 255, 255))
        d.text((58, 65), "DOW", font=_load_font(36, bold=True), fill=(220, 38, 38))
        d.text((58, 110), "JONES", font=_load_font(32, bold=True), fill=(15, 23, 42))
        d.text((48, 208), "S&P DOW JONES INDICES", font=_load_font(12, bold=True), fill=(255, 255, 255))

    # 12. Commercial Media: REUTERS, BLOOMBERG, LIVEMINT, MONEYCONTROL, ET, NDTV, TOI, COINDESK, CNBC, WSJ
    elif "REUTER" in code:
        img.paste((255, 255, 255), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        cx, cy = 120, 95
        for r_step in [20, 40, 60]:
            d.ellipse([cx - r_step, cy - r_step, cx + r_step, cy + r_step], outline=(249, 115, 22), width=5)
        d.text((52, 160), "REUTERS", font=_load_font(28, bold=True), fill=(249, 115, 22))
        d.text((48, 208), "GLOBAL FINANCIAL WIRE", font=f_sub, fill=(100, 116, 139))

    elif "BLOOM" in code:
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.text((36, 90), "Bloomberg", font=_load_font(32, bold=True), fill=(255, 255, 255))
        d.text((48, 208), "FINANCIAL MARKETS", font=f_sub, fill=(250, 204, 21))

    elif "LIVEMINT" in code or "MINT" in code:
        img.paste((254, 240, 138), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([35, 45, 205, 165], radius=16, fill=(249, 115, 22))
        d.text((60, 85), "mint", font=_load_font(42, bold=True), fill=(255, 255, 255))
        d.text((46, 208), "LIVEMINT MARKETS", font=f_sub, fill=(180, 83, 9))

    elif "MONEYCONTROL" in code:
        img.paste((240, 253, 244), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.ellipse([45, 45, 195, 165], fill=(22, 163, 74))
        d.text((64, 85), "money", font=_load_font(26, bold=True), fill=(255, 255, 255))
        d.text((62, 115), "control", font=_load_font(26, bold=True), fill=(250, 204, 21))
        d.text((44, 208), "MONEYCONTROL PRO", font=f_sub, fill=(22, 163, 74))

    elif "ET" in code or "ECONOMIC" in code:
        img.paste((254, 242, 242), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([45, 45, 195, 165], radius=16, fill=(185, 28, 28))
        d.text((75, 80), "ET", font=_load_font(52, bold=True), fill=(255, 255, 255))
        d.text((40, 208), "THE ECONOMIC TIMES", font=f_sub, fill=(185, 28, 28))

    elif "NDTV" in code:
        img.paste((239, 68, 68), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rectangle([45, 60, 195, 150], fill=(255, 255, 255))
        d.text((58, 80), "NDTV", font=_load_font(34, bold=True), fill=(239, 68, 68))
        d.text((54, 208), "NDTV PROFIT WIRE", font=f_sub, fill=(255, 255, 255))

    elif "TOI" in code or "TIMES" in code:
        img.paste((248, 250, 252), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rectangle([45, 55, 195, 155], fill=(15, 23, 42))
        d.text((70, 80), "TOI", font=_load_font(42, bold=True), fill=(250, 204, 21))
        d.text((48, 208), "TIMES OF INDIA", font=f_sub, fill=(15, 23, 42))

    elif "CNBC" in code:
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Peacock fan arcs
        cx, cy = 120, 85
        colors = [(239, 68, 68), (249, 115, 22), (234, 179, 8), (34, 197, 94), (59, 130, 246), (168, 85, 247)]
        for idx, col in enumerate(colors):
            d.pieslice([cx - 45, cy - 45, cx + 45, cy + 45], start=180 + idx * 30, end=210 + idx * 30, fill=col)
        d.text((62, 140), "CNBC", font=_load_font(32, bold=True), fill=(255, 255, 255))
        d.text((46, 208), "FIRST IN BUSINESS", font=f_sub, fill=(203, 213, 225))

    elif "WSJ" in code or "MARKETWATCH" in code:
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.text((68, 85), "WSJ", font=_load_font(44, bold=True), fill=(255, 255, 255))
        d.text((42, 208), "THE WALL STREET JOURNAL", font=_load_font(11, bold=True), fill=(203, 213, 225))

    elif "COINDESK" in code or "CRYPTO" in code:
        img.paste((24, 24, 27), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([45, 45, 195, 165], radius=16, fill=(250, 204, 21))
        d.text((64, 85), "COIN", font=_load_font(34, bold=True), fill=(24, 24, 27))
        d.text((64, 120), "DESK", font=_load_font(30, bold=True), fill=(24, 24, 27))
        d.text((54, 208), "CRYPTO & MACRO", font=f_sub, fill=(250, 204, 21))

    # 13. Multilateral: IMF, ECB, BOE, BOJ, OPEC, IFSCA, FINMIN
    elif "IMF" in code:
        img.paste((239, 246, 255), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.ellipse([45, 45, 195, 165], fill=(30, 58, 138), outline=(250, 204, 21), width=3)
        d.text((70, 85), "IMF", font=_load_font(42, bold=True), fill=(255, 255, 255))
        d.text((38, 208), "INTL MONETARY FUND", font=f_sub, fill=(30, 58, 138))

    elif "ECB" in code:
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.ellipse([45, 45, 195, 165], fill=(30, 58, 138), outline=(250, 204, 21), width=3)
        d.text((72, 85), "ECB", font=_load_font(42, bold=True), fill=(250, 204, 21))
        d.text((44, 208), "EUROPEAN CENTRAL BANK", font=f_sub, fill=(203, 213, 225))

    elif "IFSCA" in code or "GIFT" in code:
        img.paste((245, 243, 255), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.polygon([(120, 35), (195, 75), (195, 155), (120, 195), (45, 155), (45, 75)], fill=(79, 70, 229))
        d.text((58, 95), "IFSCA", font=_load_font(32, bold=True), fill=(255, 255, 255))
        d.text((54, 208), "GIFT CITY AUTHORITY", font=f_sub, fill=(79, 70, 229))

    elif "FINMIN" in code or "TREASURY" in code or "MINISTRY" in code:
        img.paste((255, 251, 235), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([45, 45, 195, 165], radius=16, fill=(180, 83, 9))
        d.text((50, 90), "FINMIN", font=_load_font(34, bold=True), fill=(255, 255, 255))
        d.text((42, 208), "MINISTRY OF FINANCE", font=f_sub, fill=(180, 83, 9))

    # 14. DEFAULT / OTHER
    else:
        img.paste((248, 250, 252), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([35, 35, 205, 185], radius=16, fill=(255, 255, 255), outline=(203, 213, 225), width=2)
        disp = code[:8] or "INST"
        d.text((65, 90), disp, font=_load_font(28, bold=True), fill=(15, 23, 42))
        d.text((48, 208), "AUTHORITY REGULATOR", font=f_sub, fill=(100, 116, 139))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 5. CORPORATE & STOCK EVENT LOGOS (FOR CALENDAR CARDS & STORIES)
# ─────────────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=128)
def generate_calendar_thumb(symbol: str = "", market: str = "", category: str = "", title: str = "") -> bytes:
    """Renders authoritative company stock logos (Reliance, TCS, Infosys, HDFC, Apple, Nvidia) or regulator emblems."""
    sym_u = (symbol or "").upper().strip()
    tit_u = (title or "").upper().strip()
    mkt_u = (market or "").upper().strip()
    cat_u = (category or "").upper().strip()
    all_text = f"{sym_u} {tit_u} {mkt_u} {cat_u}"

    # If it's a macroeconomic or regulatory event, delegate directly to the official regulatory logo!
    if any(k in all_text for k in ["SEBI", "RBI", "FED", "FOMC", "SEC", "TREASURY", "CPI", "INFLATION", "MINISTRY", "MACRO"]):
        reg = "RBI" if "RBI" in all_text else ("FED" if any(f in all_text for f in ["FED", "FOMC"]) else ("SEBI" if "SEBI" in all_text else ("SEC" if "SEC" in all_text else "GOI")))
        return generate_regulator_logo(reg)

    w, h = 240, 240
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)

    f_sym = _load_font(28, bold=True)
    f_sub = _load_font(13, bold=True)

    # 1. RELIANCE INDUSTRIES (RIL)
    if "RELIANCE" in all_text or "RIL" in all_text:
        img.paste((10, 37, 64), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Reliance emblem: Red and white flame crest inside blue field
        d.rounded_rectangle([45, 45, 195, 175], radius=16, fill=(15, 76, 129), outline=(220, 38, 38), width=3)
        d.ellipse([100, 65, 140, 105], fill=(220, 38, 38))
        d.ellipse([110, 75, 130, 95], fill=(255, 255, 255))
        d.text((54, 120), "RELIANCE", font=_load_font(26, bold=True), fill=(255, 255, 255))
        d.text((62, 208), "ENERGY & TELECOM", font=f_sub, fill=(147, 197, 253))

    # 2. TCS (Tata Consultancy Services)
    elif "TCS" in all_text or "TATA CONSULTANCY" in all_text:
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Ultramarine blue corporate card with Tata bar
        d.rounded_rectangle([35, 40, 205, 180], radius=14, fill=(30, 58, 138), outline=(59, 130, 246), width=2)
        d.text((85, 80), "TCS", font=_load_font(42, bold=True), fill=(255, 255, 255))
        d.rectangle([60, 140, 180, 146], fill=(59, 130, 246))
        d.text((54, 208), "TATA ENTERPRISE • IT", font=f_sub, fill=(147, 197, 253))

    # 3. INFOSYS (INFY)
    elif "INFOSYS" in all_text or "INFY" in all_text:
        img.paste((240, 249, 255), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([35, 40, 205, 180], radius=14, fill=(2, 132, 199), outline=(14, 165, 233), width=2)
        d.text((52, 92), "Infosys", font=_load_font(38, bold=True), fill=(255, 255, 255))
        d.text((68, 208), "GLOBAL TECH / IT", font=f_sub, fill=(2, 132, 199))

    # 4. HDFC BANK
    elif "HDFC" in all_text:
        img.paste((239, 246, 255), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Signature blue and red grid emblem
        d.rounded_rectangle([35, 40, 205, 180], radius=14, fill=(30, 58, 138))
        d.rectangle([100, 60, 140, 100], fill=(220, 38, 38))
        d.rectangle([108, 68, 132, 92], fill=(255, 255, 255))
        d.text((64, 118), "HDFC BANK", font=_load_font(22, bold=True), fill=(255, 255, 255))
        d.text((62, 208), "BANKING & FINANCE", font=f_sub, fill=(30, 58, 138))

    # 5. ICICI BANK
    elif "ICICI" in all_text:
        img.paste((255, 247, 237), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([35, 40, 205, 180], radius=14, fill=(154, 52, 18))  # Maroon-Orange
        d.text((80, 80), "icici", font=_load_font(38, bold=True), fill=(254, 215, 170))
        d.text((70, 125), "BANK", font=_load_font(24, bold=True), fill=(255, 255, 255))
        d.text((64, 208), "RETAIL BANKING", font=f_sub, fill=(154, 52, 18))

    # 6. TATA MOTORS / TATA STEEL
    elif "TATA" in all_text:
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.ellipse([45, 45, 195, 175], outline=(59, 130, 246), width=4)
        d.text((72, 85), "TATA", font=_load_font(38, bold=True), fill=(255, 255, 255))
        d.text((66, 208), "TATA GROUP CONGLOMERATE", font=_load_font(11, bold=True), fill=(147, 197, 253))

    # 7. SUN PHARMA
    elif "SUN" in all_text or "PHARMA" in all_text:
        img.paste((255, 255, 255), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.ellipse([85, 45, 155, 115], fill=(245, 158, 11))
        d.text((45, 125), "SUN PHARMA", font=_load_font(24, bold=True), fill=(30, 58, 138))
        d.text((56, 208), "PHARMACEUTICALS", font=f_sub, fill=(245, 158, 11))

    # 8. APPLE / AAPL
    elif "AAPL" in all_text or "APPLE" in all_text:
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Apple silhouette representation
        d.ellipse([80, 75, 160, 155], fill=(241, 245, 249))
        d.ellipse([70, 60, 110, 85], fill=(15, 23, 42))
        d.ellipse([140, 75, 175, 110], fill=(15, 23, 42))  # Bite
        d.text((88, 165), "Apple", font=_load_font(22, bold=True), fill=(255, 255, 255))
        d.text((70, 208), "NASDAQ: AAPL", font=f_sub, fill=(148, 163, 184))

    # 9. NVIDIA / NVDA
    elif "NVDA" in all_text or "NVIDIA" in all_text:
        img.paste((0, 0, 0), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Nvidia signature neon green eye emblem
        d.arc([60, 50, 180, 150], start=30, end=330, fill=(118, 185, 0), width=8)
        d.ellipse([100, 85, 140, 125], fill=(118, 185, 0))
        d.text((70, 155), "NVIDIA", font=_load_font(26, bold=True), fill=(255, 255, 255))
        d.text((68, 208), "AI & SEMICONDUCTORS", font=_load_font(11, bold=True), fill=(118, 185, 0))

    # 10. MICROSOFT / MSFT
    elif "MSFT" in all_text or "MICROSOFT" in all_text:
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # 4 Microsoft colored squares
        d.rectangle([75, 55, 115, 95], fill=(242, 80, 34))    # Red
        d.rectangle([125, 55, 165, 95], fill=(127, 186, 0))   # Green
        d.rectangle([75, 105, 115, 145], fill=(0, 164, 239))  # Blue
        d.rectangle([125, 105, 165, 145], fill=(255, 185, 0)) # Yellow
        d.text((64, 158), "Microsoft", font=_load_font(22, bold=True), fill=(255, 255, 255))
        d.text((72, 208), "NASDAQ: MSFT", font=f_sub, fill=(148, 163, 184))

    # DEFAULT STOCK / SCRIP (Clean Institutional Ticker Card)
    else:
        img.paste((248, 250, 252), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([35, 40, 205, 180], radius=14, fill=(255, 255, 255), outline=(226, 232, 240), width=2)
        # Exchange top pill
        d.rounded_rectangle([50, 52, 110, 74], radius=4, fill=(239, 246, 255))
        d.text((58, 55), mkt_u or "NSE", font=_load_font(12, bold=True), fill=(0, 82, 255))
        
        display_sym = (sym_u or tit_u[:8] or "STOCK")
        f_s = _load_font(28 if len(display_sym) <= 5 else 22, bold=True)
        sw = d.textlength(display_sym, font=f_s)
        d.text(((w - sw) / 2, 95), display_sym, font=f_s, fill=(15, 23, 42))
        
        d.text((58, 145), "CORP ACTION / RESULTS", font=_load_font(10, bold=True), fill=(100, 116, 139))
        d.text((56, 208), "EQUITY CATALYST", font=f_sub, fill=(0, 82, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 6. HIGH-DEFINITION EDITORIAL NEWS THUMBNAIL (240x240)
# ─────────────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=128)
def generate_news_thumb(topic: str = "", category: str = "", source: str = "", title: str = "") -> bytes:
    """Renders high-definition editorial pictures with topic imagery and source badges for news cards and stories."""
    w, h = 240, 240
    all_t = f"{topic} {category} {source} {title}".upper()
    img = Image.new("RGB", (w, h), (15, 23, 42))
    d = ImageDraw.Draw(img)

    f_badge = _load_font(12, bold=True)
    f_title = _load_font(15, bold=True)

    # 1. OIL & COMMODITIES (Crude, Brent, MCX, Natural Gas)
    if any(k in all_t for k in ["CRUDE", "OIL", "BRENT", "MCX", "COMMODITY", "PETROLEUM"]):
        # Sunset amber-slate sky
        img.paste((255, 247, 237), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Oil rig & storage tanks silhouette
        d.rectangle([0, 140, w, h], fill=(30, 41, 59))
        d.polygon([(60, 60), (40, 140), (80, 140)], fill=(15, 23, 42))     # Derrick tower
        d.line([(60, 60), (60, 140)], fill=(217, 119, 6), width=3)
        d.ellipse([120, 110, 190, 160], fill=(51, 65, 85))                # Storage tank
        d.text((25, 175), "CRUDE OIL & ENERGY", font=f_title, fill=(255, 255, 255))
        badge_txt = source[:10] or "COMMODITIES"

    # 2. GOLD & PRECIOUS METALS
    elif any(k in all_t for k in ["GOLD", "SILVER", "BULLION", "JEWELLERY"]):
        img.paste((24, 24, 27), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Stack of gold bullion bars with metallic shine
        d.polygon([(50, 120), (150, 120), (130, 150), (30, 150)], fill=(250, 204, 21))
        d.polygon([(150, 120), (190, 100), (170, 130), (130, 150)], fill=(217, 119, 6))
        d.polygon([(70, 90), (170, 90), (150, 120), (50, 120)], fill=(254, 240, 138))
        d.text((45, 175), "PRECIOUS METALS", font=f_title, fill=(250, 204, 21))
        badge_txt = source[:10] or "BULLION"

    # 3. IT & TECH (TCS, Infosys, Hiring, AI, Tech Giants)
    elif any(k in all_t for k in ["IT", "TECH", "TCS", "INFOSYS", "HIRING", "SOFTWARE", "AI"]):
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Data center servers & microchip tracks
        for gy in range(40, 140, 20):
            d.line([30, gy, 210, gy], fill=(30, 58, 138), width=1)
        for gx in range(40, 220, 30):
            d.line([gx, 40, gx, 140], fill=(30, 58, 138), width=1)
        # Illuminated CPU chip
        d.rounded_rectangle([80, 55, 160, 125], radius=10, fill=(14, 165, 233), outline=(56, 189, 248), width=2)
        d.text((105, 80), "IT", font=_load_font(26, bold=True), fill=(255, 255, 255))
        d.text((32, 175), "TECH & HIRING SURGE", font=f_title, fill=(255, 255, 255))
        badge_txt = source[:10] or "IT / TECH"

    # 4. CENTRAL BANKS & MACRO (Fed, Rates, Inflation, FOMC)
    elif any(k in all_t for k in ["FED", "RATES", "INFLATION", "FOMC", "CENTRAL BANK", "YIELDS"]):
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Neoclassical Central Bank facade columns
        d.polygon([(40, 55), (120, 25), (200, 55)], fill=(71, 85, 105))
        for col_x in [55, 85, 115, 145, 175]:
            d.rectangle([col_x, 55, col_x + 12, 130], fill=(148, 163, 184))
        d.rectangle([40, 130, 200, 145], fill=(71, 85, 105))
        d.text((42, 175), "CENTRAL BANK POLICY", font=f_title, fill=(255, 255, 255))
        badge_txt = source[:10] or "MACRO"

    # 5. TELECOM & 5G (Jio, Bharti Airtel, Telecom)
    elif any(k in all_t for k in ["TELECOM", "JIO", "AIRTEL", "5G", "MOBILE"]):
        img.paste((24, 39, 75), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # 5G Telecom transmission tower & circular radio waves
        d.polygon([(115, 45), (125, 45), (145, 145), (95, 145)], fill=(226, 232, 240))
        d.arc([80, 25, 160, 105], start=210, end=330, fill=(14, 165, 233), width=3)
        d.arc([60, 10, 180, 130], start=210, end=330, fill=(14, 165, 233), width=3)
        d.text((38, 175), "5G TELECOM NETWORK", font=f_title, fill=(255, 255, 255))
        badge_txt = source[:10] or "TELECOM"

    # 6. BANKING & LOANS (HDFC, ICICI, Banking, NPAs)
    elif any(k in all_t for k in ["BANK", "HDFC", "ICICI", "LOAN", "NPA", "CREDIT"]):
        img.paste((15, 23, 42), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Financial district skyscrapers
        d.rectangle([40, 65, 85, 145], fill=(30, 58, 138))
        d.rectangle([95, 45, 145, 145], fill=(2, 132, 199))
        d.rectangle([155, 75, 200, 145], fill=(30, 58, 138))
        d.text((38, 175), "BANKING & FINANCE", font=f_title, fill=(255, 255, 255))
        badge_txt = source[:10] or "BANKING"

    # 7. DEFAULT / D-STREET / MARKETS
    else:
        img.paste((248, 250, 252), [0, 0, w, h])
        d = ImageDraw.Draw(img)
        # Financial Candlestick chart
        d.rectangle([0, 0, w, h], fill=(248, 250, 252))
        for cx_c, h_top, h_bot, col in [
            (50, 70, 120, (16, 185, 129)),
            (90, 50, 110, (16, 185, 129)),
            (130, 80, 135, (239, 68, 68)),
            (170, 60, 105, (16, 185, 129)),
            (205, 45, 95, (16, 185, 129))
        ]:
            d.line([cx_c + 8, h_top - 15, cx_c + 8, h_bot + 15], fill=col, width=2)
            d.rectangle([cx_c, h_top, cx_c + 16, h_bot], fill=col)
        d.text((45, 175), "MARKET CATALYST", font=f_title, fill=(15, 23, 42))
        badge_txt = source[:10] or "MARKETS"

    # Top Source Pill Overlay
    d.rounded_rectangle([15, 15, 120, 38], radius=6, fill=(0, 82, 255), outline=(255, 255, 255, 80), width=1)
    d.text((24, 20), badge_txt.upper(), font=f_badge, fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def generate_placeholder_thumb(category: str = "all", source: str = "", title: str = "") -> bytes:
    """Delivers high-definition editorial pictures for news cards & story circles."""
    return generate_news_thumb(topic=category, category=category, source=source, title=title)
