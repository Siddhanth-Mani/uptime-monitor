"""Entry point: check every site, update state, write the status-page data, send alerts.

    python -m monitor.run --config sites.json --state state --out docs/data
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import alerts
from .checker import check_site
from .store import Store, slugify


def run(config_path: Path, state_dir: Path, out_dir: Path, checker=check_site, notify=alerts.send) -> dict:
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    sites = config["sites"]
    warn_days = int(config.get("cert_warning_days", 14))

    with ThreadPoolExecutor(max_workers=min(8, len(sites))) as pool:
        results = list(pool.map(lambda s: checker(s["url"], s.get("expect")), sites))

    store = Store(state_dir)
    for site, res in zip(sites, results):
        slug, r = slugify(site["name"]), res.to_dict()
        before = dict(store.status.get(slug, {}))
        change = store.record(slug, site["name"], r)
        if change == "down":
            notify(alerts.down_message(site["name"], site["url"], r["error"]))
        elif change == "up":
            notify(alerts.up_message(site["name"], site["url"], r["ts"] - before.get("since", r["ts"])))
        if store.cert_alert_due(slug, r["cert_days"], warn_days):
            notify(alerts.cert_message(site["name"], site["url"], r["cert_days"]))
        mark = "UP  " if r["ok"] else "DOWN"
        print(f"{mark} {site['name']:<34} {r['status'] or '-':>4} {str(r['ms'] or '-'):>6} ms  cert {r['cert_days']} d  {r['error'] or ''}")

    store.save()
    summary = store.summary(sites, int(time.time()), int(config.get("interval_minutes", 10)))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Check sites and update the status page data.")
    ap.add_argument("--config", default="sites.json")
    ap.add_argument("--state", default="state")
    ap.add_argument("--out", default="docs/data")
    a = ap.parse_args()
    s = run(Path(a.config), Path(a.state), Path(a.out))
    print(f"overall: {s['overall']}")


if __name__ == "__main__":
    main()
