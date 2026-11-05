#!/usr/bin/env python3
"""
Enterprise Member Gatekeeper & PIN Security Module for Global News Feed Room (GNC)
Designed for 1,000,000+ member scale with persistent storage, administrative approval,
member-chosen or admin-issued PINs/passwords, preferred language persistence, and account suspension controls.
"""

import os
import json
import time
import hashlib
import secrets
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("MemberGatekeeper")

CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")
MEMBERS_DB_FILE = os.path.join(CONFIG_DIR, "members_database.json")
AUTH_CONFIG_FILE = os.path.join(CONFIG_DIR, "security_auth.json")

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _hash_pin(pin: str, salt: Optional[str] = None) -> Tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + pin).encode('utf-8')).hexdigest()
    return hashed, salt

def _verify_pin(pin: str, hashed: str, salt: str) -> bool:
    expected, _ = _hash_pin(pin, salt)
    return secrets.compare_digest(expected, hashed)

def _generate_pin(length: int = 6) -> str:
    """Generate cryptographically secure 6 or 8 digit PIN."""
    length = 8 if length >= 8 else 6
    min_val = 10 ** (length - 1)
    max_val = (10 ** length) - 1
    return str(secrets.randbelow(max_val - min_val + 1) + min_val)

class MemberGatekeeper:
    def __init__(self, db_path: str = MEMBERS_DB_FILE):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.members: Dict[str, Dict] = {}
        self._load()
        self._ensure_seed_admin()

    def _load(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.members = data.get("members", {})
                    logger.info(f"Loaded {len(self.members)} members from {self.db_path}")
            except Exception as e:
                logger.error(f"Error reading members database: {e}")
                self.members = {}
        else:
            self.members = {}
            self._save()

    def _save(self):
        try:
            tmp = self.db_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"members": self.members, "version": "2.1", "updated_at": _now_iso()}, f, indent=2)
            os.replace(tmp, self.db_path)
        except Exception as e:
            logger.error(f"Error persisting members database: {e}")

    def _ensure_seed_admin(self):
        admin_id = "mem_admin_master"
        existing = self.members.get(admin_id, {})
        pref_lang = existing.get("preferred_language", "en")
        pin_hash, salt = _hash_pin("111111")
        self.members[admin_id] = {
            "id": admin_id,
            "name": "Eshan Parek (Master Admin)",
            "identifier": "eshanparek@gmail.com",
            "phone": "+91-9892000000",
            "auth_type": "email",
            "status": "ACTIVE",
            "role": "ADMIN",
            "pin_hash": pin_hash,
            "salt": salt,
            "pin_plaintext_admin": "111111",
            "preferred_language": pref_lang,
            "is_first_login": False,
            "created_at": existing.get("created_at") or _now_iso(),
            "approved_at": existing.get("approved_at") or _now_iso(),
            "last_login_at": existing.get("last_login_at"),
            "notes": "System Master Administrator"
        }
        self._save()

    def register_member(
        self,
        name: str = "",
        identifier: str = "",
        phone: str = "",
        auth_type: str = "email",
        pin: str = "",
        preferred_language: str = "en"
    ) -> Dict:
        """
        Register a new member in PENDING_APPROVAL status using Email, Phone Number,
        Password/PIN (fed by member), and Preferred Language.
        Once approved by Admin, the member can log in immediately using the credentials they fed.
        """
        identifier = (identifier or "").strip().lower()
        phone = (phone or "").strip()
        pin = (pin or "").strip()
        preferred_language = (preferred_language or "en").strip() or "en"

        if not identifier and phone:
            identifier = phone

        if not identifier:
            return {"status": "error", "message": "Please provide an Email Address or Phone Number."}

        # Check if already exists
        for mem in self.members.values():
            if mem["identifier"] == identifier:
                return {"status": "exists", "member": mem, "message": "An account with this email/identifier already exists."}
            if phone and mem.get("phone") == phone:
                return {"status": "exists", "member": mem, "message": "An account with this phone number already exists."}

        pin_hash = ""
        salt = ""
        pin_plain = ""
        is_first_login = True
        if pin:
            pin_hash, salt = _hash_pin(pin)
            pin_plain = pin
            is_first_login = False

        mem_id = f"mem_{int(time.time())}_{secrets.token_hex(4)}"
        display_name = (name or "").strip()
        if not display_name:
            display_name = identifier.split("@")[0] if "@" in identifier else f"Member {phone[-4:] if len(phone) >= 4 else mem_id[-4:]}"

        member = {
            "id": mem_id,
            "name": display_name,
            "identifier": identifier,
            "phone": phone,
            "auth_type": auth_type or "portal",
            "status": "PENDING_APPROVAL",
            "role": "MEMBER",
            "pin_hash": pin_hash,
            "salt": salt,
            "pin_plaintext_admin": pin_plain,
            "preferred_language": preferred_language,
            "is_first_login": is_first_login,
            "created_at": _now_iso(),
            "approved_at": None,
            "last_login_at": None,
            "notes": "Member self-registered credentials; awaiting admin approval"
        }
        self.members[mem_id] = member
        self._save()
        return {
            "status": "success",
            "member": member,
            "message": "Profile created with your credentials & preferred language! Awaiting Administrator approval in Site Settings before you can sign in."
        }

    def approve_member(self, member_id: str, pin_length: Optional[int] = None) -> Optional[Dict]:
        """
        Admin approves member.
        - If the member already set a Password/PIN during registration and pin_length is None (or 0),
          preserve the member's self-chosen Password/PIN so they can log in with the exact credentials they fed!
        - If the member has no PIN or Admin explicitly requests generating a new 6/8-digit PIN, generate one.
        """
        if member_id not in self.members:
            return None
        mem = self.members[member_id]
        has_user_pin = bool(mem.get("pin_hash") and mem.get("pin_plaintext_admin"))

        if has_user_pin and (pin_length is None or pin_length == 0):
            # Keep the user's self-registered Password/PIN intact
            mem["status"] = "ACTIVE"
            mem["approved_at"] = _now_iso()
            mem["is_first_login"] = False
        else:
            gen_len = int(pin_length) if pin_length in (6, 8) else 6
            pin = _generate_pin(gen_len)
            pin_hash, salt = _hash_pin(pin)
            mem["status"] = "ACTIVE"
            mem["pin_hash"] = pin_hash
            mem["salt"] = salt
            mem["pin_plaintext_admin"] = pin
            mem["approved_at"] = _now_iso()
            mem["is_first_login"] = True

        self._save()
        return mem

    def update_member_language(self, identifier: str, preferred_language: str) -> Dict:
        """Permanently save a member's preferred site viewing language."""
        identifier = (identifier or "").strip().lower()
        preferred_language = (preferred_language or "en").strip() or "en"
        if not identifier:
            return {"success": False, "message": "Missing member identifier."}

        target_mem = None
        for mem in self.members.values():
            if mem["identifier"].lower() == identifier or (mem.get("phone") and mem.get("phone") == identifier) or mem.get("id") == identifier:
                target_mem = mem
                break

        if not target_mem:
            return {"success": False, "message": "Member profile not found."}

        target_mem["preferred_language"] = preferred_language
        target_mem["language_updated_at"] = _now_iso()
        self._save()
        return {
            "success": True,
            "preferred_language": preferred_language,
            "member": target_mem,
            "message": f"Default language preference ({preferred_language.upper()}) permanently saved to your member profile."
        }

    def reset_member_pin(self, identifier: str, old_pin: str, new_pin: str) -> Dict:
        """Allows active member to reset their PIN/Password after authentication."""
        auth_res = self.authenticate(identifier, old_pin)
        if not auth_res["success"]:
            return {"success": False, "message": auth_res["message"]}
        
        mem = auth_res["member"]
        new_pin = new_pin.strip()
        if len(new_pin) < 4:
            return {"success": False, "message": "Password / PIN must be at least 4 characters (or 6/8 digits)."}

        pin_hash, salt = _hash_pin(new_pin)
        mem["pin_hash"] = pin_hash
        mem["salt"] = salt
        mem["pin_plaintext_admin"] = new_pin  # Kept in sync for Admin inspection
        mem["is_first_login"] = False
        mem["pin_updated_at"] = _now_iso()
        self._save()
        return {"success": True, "member": mem, "message": "Password / PIN successfully updated and saved permanently."}

    def authenticate(self, identifier: str, pin: str) -> Dict:
        """Authenticate member with their Email or Phone Number and Password/PIN."""
        identifier = (identifier or "").strip().lower()
        pin = (pin or "").strip()

        target_mem = None
        for mem in self.members.values():
            if mem["identifier"].lower() == identifier or (mem.get("phone") and mem.get("phone").strip().lower() == identifier):
                target_mem = mem
                break

        if not target_mem:
            return {"success": False, "message": "Account not found with this Email or Phone Number."}

        if target_mem["status"] == "PENDING_APPROVAL":
            return {"success": False, "message": "Your account is currently PENDING APPROVAL by the Administrator. Once approved in Site Settings, you can log in with your credentials."}

        if target_mem["status"] == "PAUSED":
            return {"success": False, "message": "Your account access has been PAUSED by the Administrator. Please contact support."}

        if target_mem["status"] != "ACTIVE":
            return {"success": False, "message": f"Account status: {target_mem['status']}. Access denied."}

        if not _verify_pin(pin, target_mem.get("pin_hash", ""), target_mem.get("salt", "")):
            return {"success": False, "message": "Incorrect Password / Security PIN. Please verify your credentials."}

        target_mem["last_login_at"] = _now_iso()
        if "preferred_language" not in target_mem:
            target_mem["preferred_language"] = "en"
        self._save()
        return {
            "success": True,
            "member": target_mem,
            "preferred_language": target_mem.get("preferred_language", "en"),
            "must_reset_pin": target_mem.get("is_first_login", False),
            "message": "Authentication successful."
        }

    def set_status(self, member_id: str, new_status: str) -> Optional[Dict]:
        """Admin can pause, activate, or reject account."""
        if member_id not in self.members:
            return None
        mem = self.members[member_id]
        mem["status"] = new_status.upper()
        self._save()
        return mem

    def delete_member(self, member_id: str) -> bool:
        if member_id in self.members:
            del self.members[member_id]
            self._save()
            return True
        return False

    def list_all_members(self) -> List[Dict]:
        return list(self.members.values())

# Global Singleton Instance
gatekeeper = MemberGatekeeper()
