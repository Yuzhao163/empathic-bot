"""
账号认证系统 — 全文件存储，无数据库
支持：匿名设备 / 邮箱密码 / Magic Link / 飞书 OAuth / 微信 OAuth
"""

import os
import json
import time
import uuid
import hashlib
import secrets
from pathlib import Path
from typing import Optional

# ============================================================================
# Paths
# ============================================================================

BASE_DIR = Path(os.getenv("MEMORY_DIR", "./memory"))
ACCOUNTS_DIR = BASE_DIR / "accounts"
SESSIONS_DIR = BASE_DIR / "sessions"
ANON_DIR = ACCOUNTS_DIR / "anonymous"

ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
ANON_DIR.mkdir(parents=True, exist_ok=True)

SESSION_TTL = 7 * 86400  # 7 days
MAGIC_LINK_TTL = 1800       # 30 minutes

# ============================================================================
# Helpers
# ============================================================================


def _account_path(user_id: str) -> Path:
    return ACCOUNTS_DIR / f"{user_id}.json"


def _session_path(token: str) -> Path:
    return SESSIONS_DIR / f"{token}.json"


def _anon_path(device_uuid: str) -> Path:
    return ANON_DIR / f"{device_uuid}.json"


def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Hash password with salt, return (hash, salt)"""
    import bcrypt
    if salt is None:
        salt = bcrypt.gensalt().decode()
    pHash = bcrypt.hashpw(password.encode(), salt.encode()).decode()
    return pHash, salt


def _verify_password(password: str, pHash: str, salt: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(password.encode(), pHash.encode())
    except Exception:
        return False


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _now() -> float:
    return time.time()


# ============================================================================
# Account Management
# ============================================================================


def create_account(
    user_id: str,
    login_method: str,  # "email" | "feishu" | "wechat" | "anonymous"
    email: str = None,
    password_hash: str = None,
    salt: str = None,
    display_name: str = None,
) -> dict:
    """Create a new account file"""
    account = {
        "user_id": user_id,
        "login_method": login_method,
        "email": email,
        "password_hash": password_hash,
        "salt": salt,
        "display_name": display_name or email or user_id,
        "created_at": _now(),
        "updated_at": _now(),
        "is_anonymous": login_method == "anonymous",
        "linked_accounts": [],  # other user_ids linked to this account
    }
    with open(_account_path(user_id), "w", encoding="utf-8") as f:
        json.dump(account, f, ensure_ascii=False, indent=2)
    # Update index
    _update_email_index(email, user_id)
    return account


def get_account(user_id: str) -> Optional[dict]:
    path = _account_path(user_id)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_account_by_email(email: str) -> Optional[dict]:
    """Look up user_id by email from index, then load account"""
    index = _load_email_index()
    user_id = index.get(email.lower())
    if not user_id:
        return None
    return get_account(user_id)


def _load_email_index() -> dict:
    """Email -> user_id reverse index"""
    idx_path = ACCOUNTS_DIR / "index.json"
    if idx_path.exists():
        with open(idx_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _update_email_index(email: str, user_id: str) -> None:
    if not email:
        return
    index = _load_email_index()
    index[email.lower()] = user_id
    with open(ACCOUNTS_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def update_account(user_id: str, updates: dict) -> None:
    account = get_account(user_id)
    if not account:
        raise ValueError(f"Account not found: {user_id}")
    account.update(updates)
    account["updated_at"] = _now()
    with open(_account_path(user_id), "w", encoding="utf-8") as f:
        json.dump(account, f, ensure_ascii=False, indent=2)


# ============================================================================
# Anonymous Account
# ============================================================================


def create_anonymous_account(device_uuid: str) -> dict:
    """Register device as anonymous account"""
    # Check if already linked
    anon = get_anonymous_link(device_uuid)
    if anon:
        account = get_account(anon["user_id"])
        if account:
            return account

    user_id = f"anon_{device_uuid}"
    account = create_account(
        user_id=user_id,
        login_method="anonymous",
        display_name=f"用户_{device_uuid[:8]}",
    )
    # Create bidirectional link
    with open(_anon_path(device_uuid), "w", encoding="utf-8") as f:
        json.dump({"user_id": user_id, "created_at": _now()}, f)
    return account


def get_anonymous_link(device_uuid: str) -> Optional[dict]:
    path = _anon_path(device_uuid)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def link_anonymous_to_account(device_uuid: str, real_user_id: str) -> None:
    """
    Upgrade anonymous account → real account
    Merge memory files: anonymous memory merged into real account
    """
    anon_link = get_anonymous_link(device_uuid)
    if not anon_link:
        return

    # Mark anonymous account as linked
    anon_user_id = anon_link["user_id"]
    update_account(anon_user_id, {
        "is_anonymous": False,
        "linked_accounts": [real_user_id],
    })

    # Merge memory files
    _merge_memory(anon_user_id, real_user_id)

    # Update anonymous link to point to real account
    with open(_anon_path(device_uuid), "w", encoding="utf-8") as f:
        json.dump({
            "user_id": real_user_id,
            "merged_from": anon_user_id,
            "linked_at": _now(),
        }, f)


def _merge_memory(from_user_id: str, to_user_id: str) -> None:
    """Append from_user's long-term memory facts to to_user's file"""
    from_path = _long_term_path(from_user_id)
    to_path = _long_term_path(to_user_id)
    if not from_path.exists() or not to_path.exists():
        # Just rename if to doesn't exist
        if from_path.exists() and not to_path.exists():
            from_path.rename(to_path)
        return

    # Append facts from 'from' to 'to'
    to_facts = _load_facts(to_path)
    from_facts = _load_facts(from_path)

    # Deduplicate by content
    existing = {f["content"] for f in to_facts}
    merged = to_facts[:]
    for fact in from_facts:
        if fact["content"] not in existing:
            merged.append(fact)

    _save_facts(to_path, merged[:100])  # Cap at 100 facts

    # Delete old file
    try:
        from_path.unlink()
    except OSError:
        pass


def _long_term_path(user_id: str) -> Path:
    return BASE_DIR / "long_term" / f"{user_id}.jsonl"


def _load_facts(path: Path) -> list:
    facts = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        facts.append(json.loads(line))
                    except Exception:
                        pass
    return facts


def _save_facts(path: Path, facts: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for fact in facts:
            f.write(json.dumps(fact, ensure_ascii=False) + "\n")


# ============================================================================
# Magic Link
# ============================================================================


def create_magic_link(email: str) -> str:
    """Create a magic link token, return the token"""
    token = _generate_token()
    magic_data = {
        "email": email.lower(),
        "token": token,
        "created_at": _now(),
        "expires_at": _now() + MAGIC_LINK_TTL,
        "used": False,
    }
    with open(SESSIONS_DIR / f"magic_{token}.json", "w", encoding="utf-8") as f:
        json.dump(magic_data, f)
    return token


def verify_magic_link(token: str) -> Optional[str]:
    """Verify magic link token, return email if valid"""
    path = SESSIONS_DIR / f"magic_{token}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data["used"] or data["expires_at"] < _now():
        return None
    data["used"] = True
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data["email"]


# ============================================================================
# Session / Token Management
# ============================================================================


def issue_session(user_id: str) -> tuple[str, dict]:
    """Create a session for logged-in user, return (token, session_info)"""
    token = _generate_token()
    session = {
        "user_id": user_id,
        "token": token,
        "created_at": _now(),
        "expires_at": _now() + SESSION_TTL,
    }
    with open(_session_path(token), "w", encoding="utf-8") as f:
        json.dump(session, f)
    return token, session


def verify_session(token: str) -> Optional[dict]:
    """Verify session token, return session info if valid"""
    path = _session_path(token)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        session = json.load(f)
    if session["expires_at"] < _now():
        path.unlink()
        return None
    return session


def revoke_session(token: str) -> None:
    path = _session_path(token)
    if path.exists():
        path.unlink()


# ============================================================================
# Auth Operations
# ============================================================================


def register_with_email(email: str, password: str, display_name: str = None) -> tuple[dict, str]:
    """
    Register new account with email + password.
    Returns (account, session_token)
    """
    existing = get_account_by_email(email)
    if existing:
        raise ValueError("Email already registered")

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    pHash, salt = _hash_password(password)
    account = create_account(
        user_id=user_id,
        login_method="email",
        email=email.lower(),
        password_hash=pHash,
        salt=salt,
        display_name=display_name or email.split("@")[0],
    )
    token, _ = issue_session(user_id)
    return account, token


def login_with_email(email: str, password: str) -> tuple[dict, str]:
    """Login with email + password, return (account, session_token)"""
    account = get_account_by_email(email)
    if not account:
        raise ValueError("Invalid email or password")
    if account["login_method"] != "email":
        raise ValueError("This account uses a different login method")
    if not _verify_password(password, account["password_hash"], account["salt"]):
        raise ValueError("Invalid email or password")
    token, _ = issue_session(account["user_id"])
    return account, token


def login_as_anonymous(device_uuid: str) -> tuple[dict, str]:
    """Login or register as anonymous device user"""
    account = create_anonymous_account(device_uuid)
    token, _ = issue_session(account["user_id"])
    return account, token


def login_with_feishu(feishu_open_id: str, display_name: str = None) -> tuple[dict, str]:
    """
    Login with Feishu Open ID.
    user_id = f"feishu_{open_id}"
    """
    user_id = f"feishu_{feishu_open_id}"
    account = get_account(user_id)
    if not account:
        account = create_account(
            user_id=user_id,
            login_method="feishu",
            display_name=display_name or f"飞书用户_{feishu_open_id[:8]}",
        )
    token, _ = issue_session(user_id)
    return account, token


def upgrade_anonymous_account(
    device_uuid: str,
    email: str,
    password: str,
    display_name: str = None,
) -> tuple[dict, str]:
    """
    Anonymous user upgrades to email account.
    Merges anonymous memory into new account.
    """
    # Check email not taken
    if get_account_by_email(email):
        raise ValueError("Email already registered")

    # Create real account
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    pHash, salt = _hash_password(password)
    account = create_account(
        user_id=user_id,
        login_method="email",
        email=email.lower(),
        password_hash=pHash,
        salt=salt,
        display_name=display_name or email.split("@")[0],
    )

    # Link & merge memory
    link_anonymous_to_account(device_uuid, user_id)

    token, _ = issue_session(user_id)
    return account, token


def get_user_info(user_id: str) -> Optional[dict]:
    """Get public user info (no sensitive fields)"""
    account = get_account(user_id)
    if not account:
        return None
    return {
        "user_id": account["user_id"],
        "display_name": account.get("display_name"),
        "login_method": account["login_method"],
        "email": account.get("email"),
        "is_anonymous": account.get("is_anonymous", False),
        "created_at": account.get("created_at"),
    }
