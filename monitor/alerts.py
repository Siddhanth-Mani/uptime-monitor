"""Telegram alerts. Optional: without TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID set, messages are only printed."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional


def _duration(seconds: int) -> str:
    m = max(0, seconds) // 60
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h} h {m} min"
    d, h = divmod(h, 24)
    return f"{d} d {h} h"


def down_message(name: str, url: str, reason: Optional[str]) -> str:
    return f"🔴 {name} is DOWN\n{url}\nReason: {reason or 'unknown'}"


def up_message(name: str, url: str, down_for: Optional[int]) -> str:
    extra = f" after {_duration(down_for)}" if down_for else ""
    return f"🟢 {name} is back UP{extra}\n{url}"


def cert_message(name: str, url: str, days: int) -> str:
    return f"🟠 {name}: TLS certificate expires in {days} day{'s' if days != 1 else ''}\n{url}"


def send(text: str) -> bool:
    """Send to Telegram if configured. Never raises: a failed alert must not fail the monitoring run."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    print("ALERT:", text.replace("\n", " | "))
    if not token or not chat:
        return False
    data = json.dumps({"chat_id": chat, "text": text, "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except OSError as exc:  # don't print the URL: it contains the token
        print(f"warning: Telegram alert failed ({type(exc).__name__})")
        return False
