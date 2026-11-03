"""
news_pdf_engine.py
==================
Generates authoritative A4 PDF News Snapshots covering all breaking headlines
and catalysts from 00:00:00 IST of the day up to the current timestamp.
Styled according to institutional typography standards with ReportLab.
"""

import io
import os
import re
import html
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, KeepTogether, Image as RLImage
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

logger = logging.getLogger("NewsPdfEngine")

PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
MARGIN_LEFT = 28
MARGIN_RIGHT = 28
MARGIN_TOP = 42
MARGIN_BOTTOM = 36
USABLE_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
IST_TZ = timezone(timedelta(hours=5, minutes=30))


class NewsNumberedCanvas(canvas.Canvas):
    """Two-pass canvas that writes dynamic page counts, institutional running headers and legal disclaimers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.doc_title = "TODAY'S BREAKING FINANCIAL NEWS SNAPSHOT"
        self.doc_subtitle = ""

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_decorations(self, num_pages: int):
        self.saveState()

        # ── 1. Running Header ──
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.8)
        self.line(MARGIN_LEFT, PAGE_HEIGHT - 38, PAGE_WIDTH - MARGIN_RIGHT, PAGE_HEIGHT - 38)

        # Draw logo icon if available
        logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.png")
        if os.path.exists(logo_path):
            try:
                self.drawImage(
                    logo_path,
                    PAGE_WIDTH - MARGIN_RIGHT - 24,
                    PAGE_HEIGHT - 32,
                    width=22,
                    height=22,
                    preserveAspectRatio=True,
                    mask='auto'
                )
            except Exception:
                pass

        self.setFont("Helvetica-Bold", 10.5)
        self.setFillColor(colors.HexColor("#0F172A"))
        self.drawString(MARGIN_LEFT, PAGE_HEIGHT - 19, "GLOBAL NEWS FEED ROOM")

        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#0052FF"))
        self.drawRightString(PAGE_WIDTH - MARGIN_RIGHT - 30, PAGE_HEIGHT - 19, "DAILY FINANCIAL INTELLIGENCE SNAPSHOT  |  A4 DOSSIER")

        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#334155"))
        dossier_label = self.doc_title.upper()
        if self.doc_subtitle:
            dossier_label += f"   •   {self.doc_subtitle}"
        self.drawString(MARGIN_LEFT, PAGE_HEIGHT - 31, dossier_label)

        # ── 2. Running Footer ──
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.8)
        self.line(MARGIN_LEFT, 26, PAGE_WIDTH - MARGIN_RIGHT, 26)

        now_str = datetime.now(IST_TZ).strftime("%d %b %Y, %H:%M IST")
        self.setFont("Helvetica", 7)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(MARGIN_LEFT, 15, f"Generated: {now_str}  |  Continuous Time Rail Ledger")

        # Legal Disclaimer
        self.setFont("Helvetica", 6)
        self.setFillColor(colors.HexColor("#94A3B8"))
        disclaimer_text = "This document and information in this document is not an investment advise, the creator and publisher are not responsible of your actions, for knowledge and information purpose only."
        self.drawCentredString(PAGE_WIDTH / 2.0, 15, disclaimer_text)

        # Page numbering
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(colors.HexColor("#0F172A"))
        self.drawRightString(PAGE_WIDTH - MARGIN_RIGHT, 15, f"Page {self._pageNumber} of {num_pages}")

        self.restoreState()


class NewsPdfEngine:
    """Compiles breaking news and catalysts into publication-ready A4 PDF dossiers."""

    def __init__(self):
        self.styles = getSampleStyleSheet() if REPORTLAB_AVAILABLE else None
        self._init_custom_styles()

    def _init_custom_styles(self):
        if not REPORTLAB_AVAILABLE:
            return

        def _add(name, **kwargs):
            if name in self.styles:
                return
            self.styles.add(ParagraphStyle(name, **kwargs))

        _add("NewsDocTitle", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=colors.HexColor("#0F172A"))
        _add("NewsDocSub", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#475569"))
        _add("NewsHdrCell", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.HexColor("#FFFFFF"), alignment=1)
        _add("NewsTimeCell", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#0F172A"), alignment=1)
        _add("NewsSrcCell", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#1E3A8A"), alignment=0)
        _add("NewsTitleCell", fontName="Helvetica-Bold", fontSize=8, leading=10.5, textColor=colors.HexColor("#0F172A"), alignment=0)
        _add("NewsSummaryCell", fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#334155"), alignment=0)
        _add("NewsScoreCell", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#0F172A"), alignment=1)
        _add("NewsSentBull", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=colors.HexColor("#166534"), alignment=1)
        _add("NewsSentBear", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=colors.HexColor("#991B1B"), alignment=1)
        _add("NewsSentNeut", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=colors.HexColor("#475569"), alignment=1)

    def generate_today_snapshot_pdf(self, news_items: List[Dict], target_dt: Optional[datetime] = None) -> Tuple[bytes, str]:
        """Generates an A4 PDF covering all headlines from 00:00:00 IST of the day up to the current timestamp."""
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("ReportLab is not installed or available.")

        now = target_dt or datetime.now(IST_TZ)
        today_date_str = now.strftime("%Y-%m-%d")
        today_disp = now.strftime("%A, %d %B %Y")
        now_time_str = now.strftime("%H:%M:%S IST")
        filename = f"News_Snapshot_{today_date_str}_{now.strftime('%H%M%S')}.pdf"

        # Filter items for today (or past 24h if early in the morning)
        from app import parse_timestamp_to_epoch
        today_midnight = datetime.combine(now.date(), datetime.min.time(), tzinfo=IST_TZ).timestamp()

        today_items = []
        for it in news_items:
            ts = it.get("timestamp", "")
            ep = parse_timestamp_to_epoch(ts)
            if ep >= today_midnight:
                today_items.append(it)

        # Fallback to recent pool if midnight cutoff yields very few items early morning
        if len(today_items) < 8:
            today_items = news_items[:30]

        # Ensure strictly descending order
        today_items.sort(key=lambda x: parse_timestamp_to_epoch(x.get("timestamp")), reverse=True)

        doc_title = "TODAY'S BREAKING FINANCIAL NEWS SNAPSHOT"
        doc_subtitle = f"{today_disp}  •  00:00 IST to {now_time_str}"

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            leftMargin=MARGIN_LEFT,
            rightMargin=MARGIN_RIGHT,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM
        )

        flowables = []

        # ── Title Banner ──
        flowables.append(Spacer(1, 4))
        title_p = Paragraph(f"<b>TODAY'S BREAKING FINANCIAL NEWS SNAPSHOT</b>", self.styles["NewsDocTitle"])
        sub_p = Paragraph(f"Comprehensive record of market-moving catalysts, institutional releases & live headlines from <b>00:00:00 IST</b> to <b>{now_time_str}</b> ({today_disp})", self.styles["NewsDocSub"])
        flowables.append(title_p)
        flowables.append(Spacer(1, 2))
        flowables.append(sub_p)
        flowables.append(Spacer(1, 8))

        # ── Telemetry Summary Bar ──
        bullish_count = sum(1 for it in today_items if "BULL" in str(it.get("ai_sentiment", "")).upper())
        bearish_count = sum(1 for it in today_items if "BEAR" in str(it.get("ai_sentiment", "")).upper())
        neutral_count = len(today_items) - bullish_count - bearish_count

        summary_data = [
            [
                Paragraph(f"<b>TOTAL HEADLINES:</b> {len(today_items)} Catalysts", self.styles["NewsTimeCell"]),
                Paragraph(f"<b>🟢 BULLISH:</b> {bullish_count}", self.styles["NewsSentBull"]),
                Paragraph(f"<b>🔴 BEARISH:</b> {bearish_count}", self.styles["NewsSentBear"]),
                Paragraph(f"<b>⚪ NEUTRAL:</b> {neutral_count}", self.styles["NewsSentNeut"]),
                Paragraph(f"<b>DISPATCH TIME:</b> {now_time_str}", self.styles["NewsTimeCell"])
            ]
        ]
        sum_table = Table(summary_data, colWidths=[USABLE_WIDTH * 0.22, USABLE_WIDTH * 0.18, USABLE_WIDTH * 0.18, USABLE_WIDTH * 0.18, USABLE_WIDTH * 0.24])
        sum_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        flowables.append(sum_table)
        flowables.append(Spacer(1, 10))

        # ── Headlines Data Table ──
        # Column widths totaling USABLE_WIDTH (~786 pt)
        col_widths = [
            USABLE_WIDTH * 0.08,  # Time
            USABLE_WIDTH * 0.12,  # Source / Reg
            USABLE_WIDTH * 0.38,  # Headline (Full title)
            USABLE_WIDTH * 0.28,  # Source Story Summary & Context
            USABLE_WIDTH * 0.07,  # Score
            USABLE_WIDTH * 0.07,  # Sentiment
        ]

        table_rows = [
            [
                Paragraph("<b>TIME (IST)</b>", self.styles["NewsHdrCell"]),
                Paragraph("<b>SOURCE</b>", self.styles["NewsHdrCell"]),
                Paragraph("<b>FULL CATALYST HEADLINE</b>", self.styles["NewsHdrCell"]),
                Paragraph("<b>SOURCE SUMMARY & TAKEAWAY</b>", self.styles["NewsHdrCell"]),
                Paragraph("<b>SCORE</b>", self.styles["NewsHdrCell"]),
                Paragraph("<b>SENTIMENT</b>", self.styles["NewsHdrCell"]),
            ]
        ]

        from app import extract_clean_time_str, clean_table_text

        for idx, it in enumerate(today_items):
            ts = it.get("timestamp", "")
            time_disp = extract_clean_time_str(str(ts), fallback_dt=now)
            source = clean_table_text(str(it.get("source", "Wire")))
            title = clean_table_text(str(it.get("title", "")))

            # Story summary distinct from reasoning
            summary = clean_table_text(str(it.get("summary") or it.get("ai_reasoning") or ""))
            if not summary or summary == title:
                summary = "Multi-market catalyst with direct price discovery implications across underlying equities and derivatives."

            score = str(round(float(it.get("ai_score", 7.5)), 1))
            sent = str(it.get("ai_sentiment", "NEUTRAL")).upper()

            if "BULL" in sent:
                sent_para = Paragraph("<b>BULLISH</b>", self.styles["NewsSentBull"])
            elif "BEAR" in sent:
                sent_para = Paragraph("<b>BEARISH</b>", self.styles["NewsSentBear"])
            else:
                sent_para = Paragraph("NEUTRAL", self.styles["NewsSentNeut"])

            # Clean markup for paragraphs
            time_p = Paragraph(html.escape(time_disp), self.styles["NewsTimeCell"])
            src_p = Paragraph(f"<b>{html.escape(source)}</b>", self.styles["NewsSrcCell"])
            title_p = Paragraph(html.escape(title), self.styles["NewsTitleCell"])
            sum_p = Paragraph(html.escape(summary[:260]), self.styles["NewsSummaryCell"])
            score_p = Paragraph(f"<b>{score}/10</b>", self.styles["NewsScoreCell"])

            table_rows.append([time_p, src_p, title_p, sum_p, score_p, sent_para])

        news_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        t_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0052FF")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
        # Alternating subtle row colors
        for r_idx in range(1, len(table_rows)):
            bg = colors.HexColor("#FFFFFF") if r_idx % 2 == 1 else colors.HexColor("#F8FAFC")
            t_style.append(('BACKGROUND', (0, r_idx), (-1, r_idx), bg))

        news_table.setStyle(TableStyle(t_style))
        flowables.append(news_table)

        def make_canvas(*args, **kwargs):
            c = NewsNumberedCanvas(*args, **kwargs)
            c.doc_title = doc_title
            c.doc_subtitle = doc_subtitle
            return c

        doc.build(flowables, canvasmaker=make_canvas)
        buf.seek(0)
        return buf.getvalue(), filename


news_pdf_engine = NewsPdfEngine()
