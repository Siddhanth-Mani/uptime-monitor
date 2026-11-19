# Uptime Monitor

A small, dependency-free uptime monitor that checks my sites every 10 minutes from GitHub Actions and publishes a live status page.

**Status page:** https://siddhanth-mani.github.io/uptime-monitor/

## What it does

- Checks each site in [`sites.json`](sites.json) for HTTP status, response time and an expected piece of text (so a blank or error page still counts as down).
- Retries once before calling a site down, so one dropped packet doesn't count as an outage.
- Reads each TLS certificate and warns 14 days before it expires.
- Opens an incident when a site goes down and closes it when the site recovers. Each one records the reason (HTTP 502, timeout, DNS, TLS…) and how long it lasted.
- Calculates uptime over 24 hours, 7 days and 30 days, and draws a 24-hour response-time chart.
- Optionally sends alerts to Telegram for down, recovered and certificate-expiring events.

## How it works

```
GitHub Actions (cron, every 10 min)
  ├─ restore history from the `data` branch
  ├─ python -m monitor.run       → check sites in parallel, update history & incidents, alert
  ├─ force-push history back to `data` (a single commit, so the repo never grows)
  └─ deploy docs/ + summary.json to GitHub Pages
```

It runs on GitHub's infrastructure rather than on the servers it watches, so it still reports when those servers are completely offline.

| Path | Purpose |
| --- | --- |
| `monitor/checker.py` | One HTTP check: status, latency, expected text, certificate expiry, readable error reasons |
| `monitor/store.py` | JSON history (31 days), incident open/close, uptime and summary maths |
| `monitor/alerts.py` | Alert wording and the optional Telegram sender (never fails a run, never logs the token) |
| `monitor/run.py` | Entry point that ties it together |
| `docs/` | Static status page with a strict CSP and no external requests. It renders with DOM APIs only (no `innerHTML`). |

## Run it locally

Python 3.10+ is needed. Nothing has to be installed.

```bash
python -m monitor.run --config sites.json --state state --out docs/data
python -m http.server -d docs 8000      # open http://localhost:8000
python -m unittest discover -s tests -t . -v
```

## Telegram alerts (optional)

1. Message [@BotFather](https://t.me/BotFather), send `/newbot` and copy the token it gives you.
2. Send any message to your new bot. Then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
3. In the repo, go to **Settings → Secrets and variables → Actions** and add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

Without these secrets, alerts are only written to the workflow log.

## Limitations

- GitHub runs scheduled workflows on a best-effort basis. Under load, runs can start several minutes late or be skipped, so the real check interval is "about 10 minutes".
- GitHub disables scheduled workflows in a public repo after 60 days with no commits. A commit, or re-enabling the workflow in the Actions tab, restarts it.
- Every check comes from one place (GitHub's US runners), so it can't tell a regional outage from a global one.
- The history is a JSON file capped at 31 days, which suits a few sites. Many sites or long retention would need a real time-series store.
