import unittest
import app as app_module


class DisabledPrintQueueTests(unittest.TestCase):
    def test_old_agent_endpoints_are_disabled(self):
        client = app_module.app.test_client()
        for path, method in (("/api/print-agent/jobs/next", "get"),
                             ("/api/print-agent/status", "get"),
                             ("/api/print-agent/jobs/1/result", "post")):
            with self.subTest(path=path):
                response = getattr(client, method)(path)
                self.assertEqual(response.status_code, 410)
                self.assertIn("desativada", response.get_json()["erro"])
