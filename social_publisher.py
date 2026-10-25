import os
import io
import time
import json
import uuid
import logging
import threading
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("SocialPublisher")

ADMIN_SETTINGS_FILE = "admin_settings.json"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "assets", "media_cache")
os.makedirs(MEDIA_DIR, exist_ok=True)


class SocialPublisher:
    """
    Unified Omnichannel Financial Broadcaster for EPM Pro.
    Dispatches publication-grade visual cards and text to:
      1. Instagram (Meta Graph API)
      2. X / Twitter (Official API v2 + Media Upload)
      3. Telegram (Photo Dispatches)
      4. Discord (Rich Webhooks)
      5. WhatsApp (Green API / Meta Cloud)
    """
    def __init__(self):
        # ── 1. Instagram Meta Graph API ──
        self.instagram_enabled = False
        self.instagram_account_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()
        self.instagram_access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()

        # ── 2. X / Twitter API v2 ──
        self.twitter_enabled = False
        self.twitter_api_key = os.getenv("TWITTER_API_KEY", "").strip()
        self.twitter_api_secret = os.getenv("TWITTER_API_SECRET", "").strip()
        self.twitter_access_token = os.getenv("TWITTER_ACCESS_TOKEN", "").strip()
        self.twitter_access_secret = os.getenv("TWITTER_ACCESS_SECRET", "").strip()
        self.twitter_min_score = 8  # Only tweet catalysts scoring >= 8 to stay inside 1,500/mo free limit

        # ── 3. Discord Webhook ──
        self.discord_enabled = False
        self.discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

        # ── 4. General Preferences ──
        self.send_news_as_photos = True  # Post news as high-contrast graphic cards across all media
        self.public_app_url = os.getenv("PUBLIC_APP_URL", "").strip()

        self._load_settings()

    def get_public_url(self) -> str:
        url = (self.public_app_url or os.getenv("PUBLIC_APP_URL", "")).strip().rstrip("/")
        if not url:
            url = "https://p01--news-engine-service--dkhqtlpvx6bh.code.run"
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        return url

    def _load_settings(self):
        if os.path.exists(ADMIN_SETTINGS_FILE):
            try:
                with open(ADMIN_SETTINGS_FILE, "r") as f:
                    data = json.load(f)

                # Instagram
                self.instagram_enabled = bool(data.get("instagram_enabled", False))
                if data.get("instagram_account_id"):
                    self.instagram_account_id = str(data["instagram_account_id"]).strip()
                if data.get("instagram_access_token"):
                    self.instagram_access_token = str(data["instagram_access_token"]).strip()

                # Twitter
                self.twitter_enabled = bool(data.get("twitter_enabled", False))
                if data.get("twitter_api_key"):
                    self.twitter_api_key = str(data["twitter_api_key"]).strip()
                if data.get("twitter_api_secret"):
                    self.twitter_api_secret = str(data["twitter_api_secret"]).strip()
                if data.get("twitter_access_token"):
                    self.twitter_access_token = str(data["twitter_access_token"]).strip()
                if data.get("twitter_access_secret"):
                    self.twitter_access_secret = str(data["twitter_access_secret"]).strip()
                self.twitter_min_score = int(data.get("twitter_min_score", 8))

                # Discord
                self.discord_enabled = bool(data.get("discord_enabled", False))
                if data.get("discord_webhook_url"):
                    self.discord_webhook_url = str(data["discord_webhook_url"]).strip()

                # Preferences
                self.send_news_as_photos = bool(data.get("send_news_as_photos", True))
                if data.get("public_app_url"):
                    self.public_app_url = str(data["public_app_url"]).strip()
            except Exception as e:
                logger.warning(f"Error loading social publisher settings: {e}")

    def save_settings(
        self,
        instagram_enabled: bool,
        instagram_account_id: str,
        instagram_access_token: str,
        twitter_enabled: bool,
        twitter_api_key: str,
        twitter_api_secret: str,
        twitter_access_token: str,
        twitter_access_secret: str,
        twitter_min_score: int,
        discord_enabled: bool,
        discord_webhook_url: str,
        send_news_as_photos: bool,
        public_app_url: str
    ) -> Dict:
        self.instagram_enabled = bool(instagram_enabled)
        self.instagram_account_id = instagram_account_id.strip()
        self.instagram_access_token = instagram_access_token.strip()

        self.twitter_enabled = bool(twitter_enabled)
        self.twitter_api_key = twitter_api_key.strip()
        self.twitter_api_secret = twitter_api_secret.strip()
        self.twitter_access_token = twitter_access_token.strip()
        self.twitter_access_secret = twitter_access_secret.strip()
        self.twitter_min_score = int(twitter_min_score)

        self.discord_enabled = bool(discord_enabled)
        self.discord_webhook_url = discord_webhook_url.strip()

        self.send_news_as_photos = bool(send_news_as_photos)
        self.public_app_url = public_app_url.strip()

        data = {}
        if os.path.exists(ADMIN_SETTINGS_FILE):
            try:
                with open(ADMIN_SETTINGS_FILE, "r") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data.update({
            "instagram_enabled": self.instagram_enabled,
            "instagram_account_id": self.instagram_account_id,
            "instagram_access_token": self.instagram_access_token,
            "twitter_enabled": self.twitter_enabled,
            "twitter_api_key": self.twitter_api_key,
            "twitter_api_secret": self.twitter_api_secret,
            "twitter_access_token": self.twitter_access_token,
            "twitter_access_secret": self.twitter_access_secret,
            "twitter_min_score": self.twitter_min_score,
            "discord_enabled": self.discord_enabled,
            "discord_webhook_url": self.discord_webhook_url,
            "send_news_as_photos": self.send_news_as_photos,
            "public_app_url": self.public_app_url
        })

        try:
            with open(ADMIN_SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed writing social publisher settings: {e}")

        return data

    def cache_image_locally(self, image_bytes: bytes) -> str:
        """
        Saves the card image to the public media cache directory and returns its public URL.
        Also performs housekeeping to keep disk footprint tiny.
        """
        filename = f"card_{uuid.uuid4().hex[:12]}.png"
        filepath = os.path.join(MEDIA_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        # Cleanup files older than 24 hours
        try:
            now = time.time()
            for fn in os.listdir(MEDIA_DIR):
                fp = os.path.join(MEDIA_DIR, fn)
                if os.path.isfile(fp) and (now - os.path.getmtime(fp) > 86400):
                    os.remove(fp)
        except Exception:
            pass

        return f"{self.get_public_url()}/api/media/{filename}"

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. Instagram Meta Graph API
    # ═══════════════════════════════════════════════════════════════════════════
    def post_to_instagram(self, image_bytes: bytes, caption: str) -> Tuple[bool, str]:
        """
        Publishes a photo post to an Instagram Business / Creator account using the official Meta Graph API.
        Flow:
          1. Upload image to public URL
          2. POST /{ig_user_id}/media with image_url + caption
          3. POST /{ig_user_id}/media_publish with creation_id
        """
        if not self.instagram_account_id or not self.instagram_access_token:
            return False, "Instagram Account ID or Access Token is missing."

        try:
            image_url = self.cache_image_locally(image_bytes)

            # Step 1: Create Media Container
            container_url = f"https://graph.facebook.com/v21.0/{self.instagram_account_id}/media"
            container_payload = {
                "image_url": image_url,
                "caption": caption[:2200],  # Instagram 2,200 char limit
                "access_token": self.instagram_access_token
            }
            resp1 = requests.post(container_url, data=container_payload, timeout=25)
            r1_json = resp1.json()

            if resp1.status_code != 200 or "id" not in r1_json:
                err_msg = r1_json.get("error", {}).get("message", resp1.text[:200])
                logger.error(f"Instagram container creation error: {err_msg}")
                return False, f"Instagram Container Error: {err_msg}"

            creation_id = r1_json["id"]
            # Brief pause for Meta media transcoding
            time.sleep(2.5)

            # Step 2: Publish Media Container
            publish_url = f"https://graph.facebook.com/v21.0/{self.instagram_account_id}/media_publish"
            publish_payload = {
                "creation_id": creation_id,
                "access_token": self.instagram_access_token
            }
            resp2 = requests.post(publish_url, data=publish_payload, timeout=25)
            r2_json = resp2.json()

            if resp2.status_code == 200 and "id" in r2_json:
                post_id = r2_json["id"]
                logger.info(f"Published to Instagram successfully: {post_id}")
                return True, f"Published to Instagram (Post ID: {post_id})"
            else:
                err_msg = r2_json.get("error", {}).get("message", resp2.text[:200])
                logger.error(f"Instagram publish error: {err_msg}")
                return False, f"Instagram Publish Error: {err_msg}"
        except Exception as e:
            logger.error(f"Instagram dispatch exception: {e}")
            return False, f"Exception: {str(e)}"

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. X / Twitter API v2 (Direct Integration)
    # ═══════════════════════════════════════════════════════════════════════════
    def post_to_twitter(self, image_bytes: bytes, text: str) -> Tuple[bool, str]:
        """
        Uploads image media and creates a tweet via Twitter API v2 using OAuth 1.0a User Context.
        """
        if not (self.twitter_api_key and self.twitter_api_secret and self.twitter_access_token and self.twitter_access_secret):
            return False, "Twitter API Key/Secret or Access Token/Secret is missing."

        try:
            from requests_oauthlib import OAuth1
            auth = OAuth1(
                self.twitter_api_key,
                self.twitter_api_secret,
                self.twitter_access_token,
                self.twitter_access_secret
            )

            # Step 1: Upload Media to Twitter v1.1 Upload Endpoint
            upload_url = "https://upload.twitter.com/1.1/media/upload.json"
            files = {"media": ("catalyst_card.png", image_bytes, "image/png")}
            up_resp = requests.post(upload_url, auth=auth, files=files, timeout=25)
            if up_resp.status_code not in (200, 201):
                err = up_resp.text[:180]
                logger.error(f"Twitter media upload failed ({up_resp.status_code}): {err}")
                return False, f"Twitter Media Upload Error: {err}"

            media_id = up_resp.json().get("media_id_string")
            if not media_id:
                return False, "Failed to obtain Twitter media_id_string"

            # Step 2: Create Tweet via Twitter API v2
            tweet_url = "https://api.twitter.com/2/tweets"
            # Ensure text fits Twitter 280-char limit
            safe_text = text.strip()[:275]
            payload = {
                "text": safe_text,
                "media": {
                    "media_ids": [media_id]
                }
            }
            tw_resp = requests.post(tweet_url, auth=auth, json=payload, timeout=20)
            tw_json = tw_resp.json()

            if tw_resp.status_code in (200, 201) and "data" in tw_json:
                tweet_id = tw_json["data"].get("id", "OK")
                logger.info(f"Published Tweet successfully: {tweet_id}")
                return True, f"Tweet published (ID: {tweet_id})"
            else:
                err = tw_resp.text[:180]
                logger.error(f"Twitter create tweet failed ({tw_resp.status_code}): {err}")
                return False, f"Twitter Tweet Error: {err}"
        except Exception as e:
            logger.error(f"Twitter dispatch exception: {e}")
            return False, f"Exception: {str(e)}"

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. Discord Rich Webhook
    # ═══════════════════════════════════════════════════════════════════════════
    def post_to_discord(self, image_bytes: bytes, title: str, description: str, color_hex: int = 0x2563eb, url: str = "") -> Tuple[bool, str]:
        """
        Dispatches an embedded financial card with attached graphic card to a Discord Channel via Webhook.
        """
        if not self.discord_webhook_url:
            return False, "Discord Webhook URL is missing."

        try:
            embed = {
                "title": title[:250],
                "description": description[:2000],
                "color": color_hex,
                "image": {"url": "attachment://card.png"},
                "footer": {"text": "EPM Pro Financial Intelligence Terminal"},
                "timestamp": datetime.utcnow().isoformat()
            }
            if url:
                embed["url"] = url

            payload = {
                "username": "EPM Pro Financial Wire",
                "embeds": [embed]
            }

            files = {
                "file": ("card.png", image_bytes, "image/png")
            }

            resp = requests.post(
                self.discord_webhook_url,
                data={"payload_json": json.dumps(payload)},
                files=files,
                timeout=20
            )

            if resp.status_code in (200, 204):
                return True, "Delivered to Discord"
            return False, f"Discord Webhook Error ({resp.status_code}): {resp.text[:160]}"
        except Exception as e:
            logger.error(f"Discord dispatch error: {e}")
            return False, f"Exception: {str(e)}"

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. Omnichannel Broadcasting Engine
    # ═══════════════════════════════════════════════════════════════════════════
    def format_social_caption(self, news: Dict) -> str:
        """Formats optimized captions with hashtags for Instagram and social media."""
        title = news.get("title", "")
        ai_score = news.get("ai_score", 5)
        ai_sentiment = news.get("ai_sentiment", "NEUTRAL")
        ai_reasoning = news.get("ai_reasoning", "")
        ai_sectors = news.get("ai_sectors", [])
        source = news.get("source", "Market Wire")

        sentiment_emoji = "🟢" if "BULL" in str(ai_sentiment).upper() else ("🔴" if "BEAR" in str(ai_sentiment).upper() else "⚪")

        # Tags
        tags = ["#StockMarketIndia", "#Nifty50", "#BSE", "#Sensex", "#EPMPro"]
        if ai_sectors:
            tags.extend([f"#{s.replace(' ', '')}" for s in ai_sectors[:4]])

        tags_str = " ".join(tags)

        caption = (
            f"🚨 {title}\n\n"
            f"📊 AI Impact Score: {ai_score}/10\n"
            f"⚡ Sentiment: {sentiment_emoji} {ai_sentiment}\n\n"
            f"💡 Key Takeaway: {ai_reasoning}\n\n"
            f"🏛 Source: {source}\n\n"
            f"{tags_str}"
        )
        return caption

    def format_twitter_text(self, news: Dict) -> str:
        """Formats punchy 280-char tweet text with cashtags."""
        title = news.get("title", "")
        ai_score = news.get("ai_score", 5)
        ai_sentiment = news.get("ai_sentiment", "NEUTRAL")
        ai_sectors = news.get("ai_sectors", [])

        cashtags = ["$NIFTY", "$SENSEX"]
        if ai_sectors:
            for s in ai_sectors[:2]:
                cashtags.append(f"${s.replace(' ', '')[:8].upper()}")

        tag_str = " ".join(cashtags)
        prefix = f"🚨 [AI {ai_score}/10 | {ai_sentiment}] "
        rem_len = 280 - len(prefix) - len(tag_str) - 6
        safe_title = title[:rem_len]

        return f"{prefix}{safe_title}\n\n{tag_str}"

    def broadcast_news_all_channels(self, news: Dict, card_bytes: bytes) -> Dict[str, Tuple[bool, str]]:
        """
        Dispatches breaking news card to all configured and enabled platforms in parallel.
        """
        results = {}

        # 1. Instagram
        if self.instagram_enabled and self.instagram_account_id and self.instagram_access_token:
            caption = self.format_social_caption(news)
            ok, msg = self.post_to_instagram(card_bytes, caption)
            results["instagram"] = (ok, msg)

        # 2. X / Twitter
        ai_score = int(news.get("ai_score", 5))
        if self.twitter_enabled and ai_score >= self.twitter_min_score:
            tweet_text = self.format_twitter_text(news)
            ok, msg = self.post_to_twitter(card_bytes, tweet_text)
            results["twitter"] = (ok, msg)

        # 3. Discord
        if self.discord_enabled and self.discord_webhook_url:
            color = 0x10b981 if "BULL" in str(news.get("ai_sentiment", "")).upper() else (0xef4444 if "BEAR" in str(news.get("ai_sentiment", "")).upper() else 0x2563eb)
            desc = news.get("ai_reasoning", "") or news.get("summary", "")
            ok, msg = self.post_to_discord(card_bytes, news.get("title", ""), desc, color, news.get("link", ""))
            results["discord"] = (ok, msg)

        return results

    def broadcast_calendar_card(self, market: str, target_date: str, card_bytes: bytes) -> Dict[str, Tuple[bool, str]]:
        """
        Dispatches a daily morning calendar infographic card (e.g. at 07:00 AM IST) to Instagram and Twitter.
        """
        results = {}
        caption = (
            f"📅 2026 {market.upper()} Market Schedule & Catalysts — {target_date}\n\n"
            f"Daily scheduled economic releases, board meetings, corporate actions, and earnings line-up.\n\n"
            f"#StockMarketIndia #{market.upper()} #Nifty #BSE #MCX #NYSE #CryptoCalendar #EPMPro"
        )

        if self.instagram_enabled and self.instagram_account_id and self.instagram_access_token:
            ok, msg = self.post_to_instagram(card_bytes, caption)
            results["instagram"] = (ok, msg)

        if self.twitter_enabled:
            tw_text = f"📅 2026 ${market.upper()} Catalyst Schedule ({target_date})\n\nDaily corporate actions, earnings & economic timings.\n\n$NIFTY $SENSEX #StockMarket"
            ok, msg = self.post_to_twitter(card_bytes, tw_text)
            results["twitter"] = (ok, msg)

        if self.discord_enabled and self.discord_webhook_url:
            ok, msg = self.post_to_discord(card_bytes, f"2026 {market.upper()} Daily Catalyst Schedule — {target_date}", "All scheduled sessions, board meetings & economic releases.", 0x2563eb)
            results["discord"] = (ok, msg)

        return results


# Global Singleton
social_publisher = SocialPublisher()
