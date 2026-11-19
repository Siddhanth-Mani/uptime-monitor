import json
import tempfile
import unittest
from pathlib import Path

from monitor.store import DAY, KEEP_SECONDS, Store, slugify


def res(ts, ok=True, ms=100, status=200, error=None, cert=60):
    return {"ts": ts, "ok": ok, "status": status if ok else None, "ms": ms if ok else None,
            "error": None if ok else (error or "Timed out"), "cert_days": cert}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_slugify(self):
        self.assertEqual(slugify("Portfolio origin (GitHub Pages)"), "portfolio-origin-github-pages")
        self.assertEqual(slugify("!!!"), "site")

    def test_first_check_up_is_not_a_change(self):
        self.assertIsNone(self.store.record("a", "A", res(1000)))

    def test_first_check_down_opens_incident(self):
        self.assertEqual(self.store.record("a", "A", res(1000, ok=False, error="HTTP 502")), "down")
        self.assertEqual(self.store.incidents[0]["reason"], "HTTP 502")
        self.assertIsNone(self.store.incidents[0]["end"])

    def test_down_then_up_closes_incident(self):
        self.store.record("a", "A", res(1000))
        self.assertEqual(self.store.record("a", "A", res(1600, ok=False)), "down")
        self.assertIsNone(self.store.record("a", "A", res(2200, ok=False)))  # still down: no repeat alert
        self.assertEqual(self.store.record("a", "A", res(2800)), "up")
        self.assertEqual(len(self.store.incidents), 1)
        self.assertEqual(self.store.incidents[0]["end"], 2800)
        self.assertEqual(self.store.status["a"]["since"], 2800)

    def test_incident_closes_only_for_its_own_site(self):
        self.store.record("a", "A", res(1000, ok=False))
        self.store.record("b", "B", res(1000, ok=False))
        self.store.record("a", "A", res(1600))
        open_ = {i["slug"]: i["end"] for i in self.store.incidents}
        self.assertEqual(open_, {"a": 1600, "b": None})

    def test_old_history_is_trimmed(self):
        self.store.record("a", "A", res(0))
        self.store.record("a", "A", res(KEEP_SECONDS + 10))
        self.assertEqual(len(self.store.history["a"]), 1)

    def test_uptime(self):
        now = 10 * DAY
        for i in range(10):
            self.store.record("a", "A", res(now - i * 600, ok=i != 0))
        self.assertEqual(self.store.uptime("a", now, DAY), 90.0)
        self.assertIsNone(self.store.uptime("missing", now, DAY))

    def test_cert_alert_fires_once_and_rearms(self):
        self.store.record("a", "A", res(1000))
        self.assertFalse(self.store.cert_alert_due("a", 30, 14))
        self.assertTrue(self.store.cert_alert_due("a", 14, 14))
        self.assertFalse(self.store.cert_alert_due("a", 13, 14))
        self.assertFalse(self.store.cert_alert_due("a", 89, 14))   # renewed: re-arm
        self.assertTrue(self.store.cert_alert_due("a", 10, 14))
        self.assertFalse(self.store.cert_alert_due("a", None, 14))

    def test_save_and_reload(self):
        self.store.record("a", "A", res(1000, ok=False))
        self.store.save()
        again = Store(Path(self.tmp.name))
        self.assertEqual(again.history, self.store.history)
        self.assertEqual(again.incidents, self.store.incidents)
        self.assertFalse(again.status["a"]["ok"])

    def test_corrupt_state_starts_fresh(self):
        Path(self.tmp.name, "history.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(Store(Path(self.tmp.name)).history, {})

    def test_summary(self):
        now = 5 * DAY
        sites = [{"name": "A", "url": "https://a"}, {"name": "B", "url": "https://b"}, {"name": "C", "url": "https://c"}]
        self.store.record("a", "A", res(now - 600, ms=100))
        self.store.record("a", "A", res(now, ms=300))
        self.store.record("b", "B", res(now, ok=False))
        s = self.store.summary(sites, now, 10)
        self.assertEqual(s["overall"], "partial")
        a, b, c = s["sites"]
        self.assertEqual(a["avg_ms_24h"], 200)
        self.assertEqual(len(a["spark"]), 2)
        self.assertEqual(a["uptime"]["h24"], 100.0)
        self.assertFalse(b["ok"])
        self.assertIsNone(c["ok"])
        json.dumps(s)  # must be serialisable

    def test_overall_states(self):
        sites = [{"name": "A", "url": "u"}]
        self.assertEqual(self.store.summary(sites, 100, 10)["overall"], "unknown")
        self.store.record("a", "A", res(100))
        self.assertEqual(self.store.summary(sites, 100, 10)["overall"], "ok")
        self.store.record("a", "A", res(200, ok=False))
        self.assertEqual(self.store.summary(sites, 200, 10)["overall"], "down")


if __name__ == "__main__":
    unittest.main()
