#!/usr/bin/env python3
"""
Enterprise Member Gatekeeper & PIN Security Module for Global News Feed Room (GNC)
Designed for 1,000,000+ member scale with persistent storage, administrative approval,
configurable 6/8 digit PINs, first-time PIN reset, and account suspension controls.
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
                json.dump({"members": self.members, "version": "2.0", "updated_at": _now_iso()}, f, indent=2)
            os.replace(tmp, self.db_path)
        except Exception as e:
            logger.error(f"Error persisting members database: {e}")

    def _ensure_seed_admin(self):
        # Admin is seed member
        admin_id = "mem_admin_master"
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
            "is_first_login": False,
            "created_at": _now_iso(),
            "approved_at": _now_iso(),
            "last_login_at": None,
            "notes": "System Master Administrator"
        }
        self._save()

    def register_member(self, name: str, identifier: str, phone: str = "", auth_type: str = "email") -> Dict:
        """Register a new member in PENDING_APPROVAL status."""
        identifier = identifier.strip().lower()
        # Check if already exists
        for mem in self.members.values():
            if mem["identifier"] == identifier:
                return {"status": "exists", "member": mem, "message": "An account with this email/username already exists."}
            if phone and mem.get("phone") == phone:
                return {"status": "exists", "member": mem, "message": "An account with this phone number already exists."}

        mem_id = f"mem_{int(time.time())}_{secrets.token_hex(4)}"
        member = {
            "id": mem_id,
            "name": name.strip() or "Registered Member",
            "identifier": identifier,
            "phone": phone.strip(),
            "auth_type": auth_type,
            "status": "PENDING_APPROVAL",
            "role": "MEMBER",
            "pin_hash": "",
            "salt": "",
            "pin_plaintext_admin": "",
            "is_first_login": True,
            "created_at": _now_iso(),
            "approved_at": None,
            "last_login_at": None,
            "notes": "Awaiting admin authorization"
        }
        self.members[mem_id] = member
        self._save()
        return {"status": "success", "member": member, "message": "Account created. Awaiting administrator approval and PIN issuance."}

    def approve_member(self, member_id: str, pin_length: int = 6) -> Optional[Dict]:
        """Admin approves member and generates initial 6 or 8 digit PIN."""
        if member_id not in self.members:
            return None
        mem = self.members[member_id]
        pin = _generate_pin(pin_length)
        pin_hash, salt = _hash_pin(pin)
        
        mem["status"] = "ACTIVE"
        mem["pin_hash"] = pin_hash
        mem["salt"] = salt
        mem["pin_plaintext_admin"] = pin  # Visible strictly to Admin in Settings table
        mem["approved_at"] = _now_iso()
        mem["is_first_login"] = True  # Allows user to reset on first login
        self._save()
        return mem

    def reset_member_pin(self, identifier: str, old_pin: str, new_pin: str) -> Dict:
        """Allows active member to reset their PIN after authentication."""
        auth_res = self.authenticate(identifier, old_pin)
        if not auth_res["success"]:
            return {"success": False, "message": auth_res["message"]}
        
        mem = auth_res["member"]
        new_pin = new_pin.strip()
        if not (len(new_pin) in (6, 8) and new_pin.isdigit()):
            return {"success": False, "message": "PIN must be exactly 6 or 8 digits."}

        pin_hash, salt = _hash_pin(new_pin)
        mem["pin_hash"] = pin_hash
        mem["salt"] = salt
        mem["pin_plaintext_admin"] = new_pin  # Kept in sync for Admin inspection
        mem["is_first_login"] = False
        mem["pin_updated_at"] = _now_iso()
        self._save()
        return {"success": True, "message": "PIN successfully updated and saved permanently."}

    def authenticate(self, identifier: str, pin: str) -> Dict:
        """Authenticate member with their identifier and 6/8-digit PIN."""
        identifier = identifier.strip().lower()
        pin = pin.strip()

        target_mem = None
        for mem in self.members.values():
            if mem["identifier"] == identifier or mem.get("phone") == identifier:
                target_mem = mem
                break

        if not target_mem:
            return {"success": False, "message": "Account not found with this identifier."}

        if target_mem["status"] == "PENDING_APPROVAL":
            return {"success": False, "message": "Your account is currently PENDING APPROVAL by the Administrator. Please wait for authorization."}

        if target_mem["status"] == "PAUSED":
            return {"success": False, "message": "Your account access has been PAUSED by the Administrator. Please contact support."}

        if target_mem["status"] != "ACTIVE":
            return {"success": False, "message": f"Account status: {target_mem['status']}. Access denied."}

        if not _verify_pin(pin, target_mem.get("pin_hash", ""), target_mem.get("salt", "")):
            return {"success": False, "message": "Incorrect Security PIN. Please verify your credentials."}

        target_mem["last_login_at"] = _now_iso()
        self._save()
        return {
            "success": True,
            "member": target_mem,
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
