import io
import os
import html
from typing import List, Dict, Optional
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


def generate_placeholder_thumb(category: str = "all", source: str = "", title: str = "") -> bytes:
    """Renders a sharp, high-contrast 120x120 editorial category icon thumbnail for news cards & story circles."""
    w, h = 120, 120
    cat_u = (category or "").lower()
    src_u = (source or "").upper()
    tit_u = (title or "").upper()

    # Theme selection based on category/source
    if "SEBI" in src_u or "SEBI" in tit_u:
        bg, fg, symbol, label = (239, 246, 255), (0, 82, 255), "🛡️", "SEBI"
    elif "RBI" in src_u or "RBI" in tit_u:
        bg, fg, symbol, label = (240, 253, 250), (13, 148, 136), "🏦", "RBI"
    elif any(k in src_u + tit_u for k in ["CRUDE", "OIL", "MCX", "COMMODITY", "GOLD"]):
        bg, fg, symbol, label = (254, 243, 199), (217, 119, 6), "⛽", "MCX"
    elif any(k in src_u + tit_u for k in ["FOMC", "FED", "US", "GLOBAL"]):
        bg, fg, symbol, label = (245, 243, 255), (124, 58, 237), "🌐", "GLOBAL"
    elif any(k in src_u + tit_u for k in ["BEAR", "FALL", "SLIP", "LOSS"]):
        bg, fg, symbol, label = (254, 242, 242), (220, 38, 38), "📉", "ALERT"
    else:
        bg, fg, symbol, label = (241, 245, 249), (71, 85, 105), "⚡", "MARKET"

    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)

    f_sym = _load_font(38, bold=True)
    f_lbl = _load_font(14, bold=True)

    # Inner border
    d.rounded_rectangle([4, 4, w - 4, h - 4], radius=10, outline=(226, 232, 240), width=1)

    # Symbol & Label
    sw = d.textlength(symbol, font=f_sym)
    d.text(((w - sw) / 2, 22), symbol, font=f_sym, fill=fg)

    lw = d.textlength(label, font=f_lbl)
    d.text(((w - lw) / 2, 78), label, font=f_lbl, fill=fg)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
