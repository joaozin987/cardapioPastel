import os
import tempfile
import unittest
from pathlib import Path

import database
import app as app_module


class PrintQueueApiTests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_profiles = app_module.PROFILES.copy()
        self.original_token = os.environ.get("PRINT_AGENT_TOKEN")
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        database.init_db()
        app_module.PROFILES["employee"] = (
            "station-1", "Funcionário", "test-pin", "station"
        )
        app_module.app.config.update(TESTING=True)
        os.environ["PRINT_AGENT_TOKEN"] = "test-agent-token"
        self.client = app_module.app.test_client()
        login = self.client.post(
            "/api/auth/login",
            json={"account": "employee", "credential": "test-pin"},
        )
        self.assertEqual(login.status_code, 200)
        self.csrf = login.get_json()["csrf_token"]

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        app_module.PROFILES.clear()
        app_module.PROFILES.update(self.original_profiles)
        if self.original_token is None:
            os.environ.pop("PRINT_AGENT_TOKEN", None)
        else:
            os.environ["PRINT_AGENT_TOKEN"] = self.original_token
        self.temp_dir.cleanup()

    def test_order_is_queued_and_agent_can_claim_and_confirm(self):
        response = self.client.post(
            "/api/pedidos",
            headers={"X-CSRF-Token": self.csrf},
            json={"itens": [{"id": 1, "q": 1}]},
        )
        self.assertEqual(response.status_code, 201)
        order_id = response.get_json()["pedido"]["id"]

        conn = database.get_connection()
        try:
            queued = conn.execute(
                "SELECT status,payload FROM print_jobs WHERE pedido_id=?",
                (order_id,),
            ).fetchone()
            self.assertIsNotNone(queued)
            self.assertEqual(queued["status"], "pendente")
            self.assertIn("Pastel", queued["payload"])
        finally:
            conn.close()

        headers = {
            "X-Print-Agent-Token": "test-agent-token",
            "X-Print-Agent-Id": "test-esp32",
        }
        claimed = self.client.get(
            "/api/print-agent/jobs/next?station_id=station-1",
            headers=headers,
        )
        self.assertEqual(claimed.status_code, 200)
        job = claimed.get_json()["job"]
        self.assertEqual(job["pedido_id"], order_id)

        completed = self.client.post(
            f"/api/print-agent/jobs/{job['id']}/result",
            headers=headers,
            json={"station_id": "station-1", "success": True},
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.get_json()["status"], "impresso")

    def test_agent_rejects_wrong_token(self):
        response = self.client.get(
            "/api/print-agent/jobs/next?station_id=station-1",
            headers={"X-Print-Agent-Token": "wrong"},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
