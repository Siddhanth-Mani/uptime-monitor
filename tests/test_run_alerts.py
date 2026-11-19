import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from monitor import alerts
from monitor.checker import CheckResult
from monitor.run import run


class AlertTextTests(unittest.TestCase):
    def test_messages(self):
        self.assertIn("DOWN", alerts.down_message("A", "https://a", "HTTP 502"))
        self.assertIn("HTTP 502", alerts.down_message("A", "https://a", "HTTP 502"))
        self.assertIn("after 1 h 5 min", alerts.up_message("A", "https://a", 3900))
        self.assertNotIn("after", alerts.up_message("A", "https://a", 0))
        self.assertIn("1 day\n", alerts.cert_message("A", "https://a", 1))
        self.assertIn("2 days", alerts.cert_message("A", "https://a", 2))

    def test_duration(self):
        self.assertEqual(alerts._duration(59), "0 min")
        self.assertEqual(alerts._duration(2 * 86400 + 3 * 3600), "2 d 3 h")

    def test_send_without_config_only_prints(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("urllib.request.urlopen") as op:
            self.assertFalse(alerts.send("hi"))
            op.assert_not_called()

    def test_send_failure_never_raises_or_leaks_token(self):
        env = {"TELEGRAM_BOT_TOKEN": "SECRET123", "TELEGRAM_CHAT_ID": "1"}
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch("urllib.request.urlopen", side_effect=OSError("no network")), \
             mock.patch("builtins.print") as pr:
            self.assertFalse(alerts.send("hi"))
        printed = " ".join(str(a) for c in pr.call_args_list for a in c.args)
        self.assertNotIn("SECRET123", printed)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config = root / "sites.json"
        self.config.write_text(json.dumps({"interval_minutes": 10, "cert_warning_days": 14, "sites": [
            {"name": "Site A", "url": "https://a.example"}]}), encoding="utf-8")
        self.state, self.out = root / "state", root / "out"
        self.sent = []

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, ok, ts, cert=60):
        result = CheckResult(ts=ts, ok=ok, status=200 if ok else None, ms=120 if ok else None,
                             error=None if ok else "Timed out", cert_days=cert)
        with mock.patch("builtins.print"):
            return run(self.config, self.state, self.out, checker=lambda u, e: result, notify=self.sent.append)

    def test_full_cycle(self):
        self.go(True, 1000)
        self.assertEqual(self.sent, [])
        self.go(False, 1600)
        self.go(False, 2200)
        self.go(True, 2800, cert=10)
        self.assertEqual(len(self.sent), 3)
        self.assertIn("DOWN", self.sent[0])
        self.assertIn("back UP after 20 min", self.sent[1])
        self.assertIn("expires in 10 days", self.sent[2])
        summary = json.loads((self.out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["overall"], "ok")
        self.assertEqual(summary["incidents"][0]["end"], 2800)
        self.assertTrue((self.state / "history.json").exists())


if __name__ == "__main__":
    unittest.main()
