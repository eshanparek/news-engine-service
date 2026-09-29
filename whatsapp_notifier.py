import os
import time
import logging
import requests
from typing import Dict
from urllib.parse import quote

logger = logging.getLogger("WhatsAppNotifier")

class WhatsAppNotifier:
    """
    Sends breaking news and market catalyst alerts to WhatsApp Channels / Groups.
    Supports:
    1. Generic Webhook (Zapier, Make, Green API, Evolution API, Wabox, etc.)
    2. Meta Cloud API (Official WhatsApp Business API)
    3. CallMeBot API (Free single-endpoint personal/group gateway)
    """
    def __init__(self):
        self.enabled = os.getenv("ENABLE_WHATSAPP_ALERTS", "false").lower() == "true"
        self.webhook_url = os.getenv("WHATSAPP_WEBHOOK_URL", "").strip()
        
        # Meta Cloud API Config
        self.meta_token = os.getenv("WHATSAPP_META_TOKEN", "").strip()
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
        self.recipient_id = os.getenv("WHATSAPP_RECIPIENT_ID", "").strip() # Channel ID / Group JID / Phone Number
        
        # CallMeBot Free API Config
        self.callmebot_phone = os.getenv("CALLMEBOT_PHONE", "").strip()
        self.callmebot_apikey = os.getenv("CALLMEBOT_APIKEY", "").strip()

    def is_configured(self) -> bool:
        return bool(
            self.webhook_url or 
            (self.meta_token and self.phone_number_id and self.recipient_id) or
            (self.callmebot_phone and self.callmebot_apikey)
        )

    def format_whatsapp_message(self, news: Dict) -> str:
        ai_score = news.get("ai_score", 5)
        ai_sentiment = news.get("ai_sentiment", "NEUTRAL")
        ai_impact = news.get("ai_impact", "MEDIUM")
        ai_reasoning = news.get("ai_reasoning", "")
        ai_sectors = news.get("ai_sectors", [])
        relevance = news.get("relevance", 0)
        source = news.get("source", "Market Wire")
        title = news.get("title", "")
        link = news.get("link", "")

        is_high_impact = (ai_score >= 8) or (ai_impact == "HIGH") or (relevance >= 80)

        sentiment_label = "🟢 BULLISH" if ai_sentiment == "BULLISH" else ("🔴 BEARISH" if ai_sentiment == "BEARISH" else "⚪ NEUTRAL")
        sectors_str = ", ".join(ai_sectors) if ai_sectors else "Broad Market"

        if is_high_impact:
            header = "🚨 *HIGH IMPACT MARKET CATALYST* 🚨\n━━━━━━━━━━━━━━━━━━━━━━"
            score_line = f"🔥 *AI Impact Score:* *{ai_score}/10 [HIGH VOLATILITY]*"
        else:
            header = "📰 *MARKET NEWS UPDATE*\n──────────────────────"
            score_line = f"🤖 *AI Impact Score:* {ai_score}/10"

        context_block = f"\n💡 *Analysis:* _{ai_reasoning}_" if ai_reasoning else ""

        text = (
            f"{header}\n\n"
            f"*{title}*\n\n"
            f"{score_line}\n"
            f"📊 *Sentiment:* {sentiment_label}\n"
            f"🎯 *Affected:* {sectors_str}"
            f"{context_block}\n\n"
            f"🏛 *Source:* {source} | *Relevance:* {relevance}%\n"
            f"🔗 {link}"
        )
        return text

    def send_news_alert(self, news: Dict) -> bool:
        if not self.enabled or not self.is_configured():
            return False

        message = self.format_whatsapp_message(news)

        # 1. Custom Webhook (Green API / Zapier / Make / Evolution API / Custom Bot Gateway)
        if self.webhook_url:
            try:
                payload = {
                    "text": message,
                    "message": message,
                    "title": news.get("title", ""),
                    "score": news.get("ai_score", 5),
                    "sentiment": news.get("ai_sentiment", "NEUTRAL"),
                    "link": news.get("link", ""),
                    "source": news.get("source", "")
                }
                resp = requests.post(self.webhook_url, json=payload, timeout=5)
                if resp.status_code in (200, 201, 202):
                    logger.info(f"[WHATSAPP WEBHOOK] Dispatched: {news.get('title', '')[:30]}...")
                    return True
                else:
                    logger.warning(f"WhatsApp Webhook returned {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                logger.error(f"WhatsApp Webhook error: {e}")

        # 2. Meta Official Cloud API
        if self.meta_token and self.phone_number_id and self.recipient_id:
            try:
                url = f"https://graph.facebook.com/v19.0/{self.phone_number_id}/messages"
                headers = {
                    "Authorization": f"Bearer {self.meta_token}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": self.recipient_id,
                    "type": "text",
                    "text": {"preview_url": True, "body": message}
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=5)
                if resp.status_code == 200:
                    logger.info(f"[WHATSAPP META] Dispatched: {news.get('title', '')[:30]}...")
                    return True
                else:
                    logger.warning(f"Meta WhatsApp API returned {resp.status_code}: {resp.text[:100]}")
            except Exception as e:
                logger.error(f"Meta WhatsApp API error: {e}")

        # 3. CallMeBot Gateway
        if self.callmebot_phone and self.callmebot_apikey:
            try:
                encoded_msg = quote(message)
                url = f"https://api.callmebot.com/whatsapp.php?phone={self.callmebot_phone}&text={encoded_msg}&apikey={self.callmebot_apikey}"
                resp = requests.get(url, timeout=6)
                if resp.status_code == 200:
                    logger.info(f"[CALLMEBOT] Dispatched: {news.get('title', '')[:30]}...")
                    return True
            except Exception as e:
                logger.error(f"CallMeBot error: {e}")

        return False

# Global instance
whatsapp_notifier = WhatsAppNotifier()
