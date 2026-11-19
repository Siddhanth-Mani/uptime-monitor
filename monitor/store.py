"""History of checks, open/closed incidents and the summary the status page reads.

State lives in plain JSON files so it can be stored on a git branch between runs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

DAY = 86400
KEEP_SECONDS = 31 * DAY        # history kept per site
KEEP_INCIDENTS = 50
SPARK_SECONDS = DAY            # the response-time chart shows the last 24 hours


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "site"


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


class Store:
    """history: {slug: [[ts, ok, ms, status], ...]}; incidents: newest first; status: last known state per site."""

    def __init__(self, state_dir: Path):
        self.dir = Path(state_dir)
        self.history: dict[str, list[list]] = _read(self.dir / "history.json", {})
        self.incidents: list[dict] = _read(self.dir / "incidents.json", [])
        self.status: dict[str, dict] = _read(self.dir / "status.json", {})

    def save(self) -> None:
        _write(self.dir / "history.json", self.history)
        _write(self.dir / "incidents.json", self.incidents)
        _write(self.dir / "status.json", self.status)

    # ---- recording -------------------------------------------------------
    def record(self, slug: str, name: str, result: dict) -> Optional[str]:
        """Store one check. Returns "down", "up" or None to say whether the site changed state."""
        rows = self.history.setdefault(slug, [])
        rows.append([result["ts"], 1 if result["ok"] else 0, result["ms"], result["status"]])
        cutoff = result["ts"] - KEEP_SECONDS
        self.history[slug] = [r for r in rows if r[0] >= cutoff]

        prev = self.status.get(slug)
        st = self.status.setdefault(slug, {"ok": result["ok"], "since": result["ts"], "cert_alerted": False})
        change = None
        if prev is None:
            change = None if result["ok"] else "down"
        elif prev["ok"] and not result["ok"]:
            change = "down"
        elif not prev["ok"] and result["ok"]:
            change = "up"

        if change:
            st["ok"], st["since"] = result["ok"], result["ts"]
        if change == "down":
            self.incidents.insert(0, {"site": name, "slug": slug, "start": result["ts"], "end": None,
                                      "reason": result.get("error") or "Down"})
        elif change == "up":
            for inc in self.incidents:
                if inc["slug"] == slug and inc["end"] is None:
                    inc["end"] = result["ts"]
                    break
        del self.incidents[KEEP_INCIDENTS:]
        st["last"] = result
        return change

    def cert_alert_due(self, slug: str, days: Optional[int], warn_days: int) -> bool:
        """True once when a certificate drops to `warn_days` or fewer; re-arms after it is renewed."""
        st = self.status.get(slug)
        if st is None or days is None:
            return False
        if days <= warn_days and not st.get("cert_alerted"):
            st["cert_alerted"] = True
            return True
        if days > warn_days:
            st["cert_alerted"] = False
        return False

    # ---- reporting -------------------------------------------------------
    def uptime(self, slug: str, now: int, seconds: int) -> Optional[float]:
        rows = [r for r in self.history.get(slug, []) if r[0] > now - seconds]
        if not rows:
            return None
        return round(100.0 * sum(r[1] for r in rows) / len(rows), 3)

    def summary(self, sites: list[dict], now: int, interval_minutes: int) -> dict:
        out = []
        for site in sites:
            slug = slugify(site["name"])
            st = self.status.get(slug, {})
            rows = self.history.get(slug, [])
            day = [r for r in rows if r[0] > now - SPARK_SECONDS]
            ok_ms = [r[2] for r in day if r[1] and r[2] is not None]
            out.append({
                "name": site["name"],
                "slug": slug,
                "url": site["url"],
                "ok": st.get("ok"),
                "since": st.get("since"),
                "last": st.get("last"),
                "uptime": {"h24": self.uptime(slug, now, DAY),
                           "d7": self.uptime(slug, now, 7 * DAY),
                           "d30": self.uptime(slug, now, 30 * DAY)},
                "avg_ms_24h": round(sum(ok_ms) / len(ok_ms)) if ok_ms else None,
                "spark": [[r[0], r[2], r[1]] for r in day],
            })
        known = [s["ok"] for s in out if s["ok"] is not None]
        overall = "unknown" if not known else "ok" if all(known) else "down" if not any(known) else "partial"
        return {"generated": now, "interval_minutes": interval_minutes, "overall": overall,
                "sites": out, "incidents": self.incidents[:20]}
