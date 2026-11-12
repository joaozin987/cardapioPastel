from datetime import datetime, timedelta
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch

import database

# The application initializes SQLite at import time; never use instance/ here.
with tempfile.TemporaryDirectory() as import_dir:
    with patch.object(database, "DB_PATH", Path(import_dir) / "import.db"):
        import app as app_module


class PrintDestinationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, "DB_PATH", Path(self.directory.name) / "test.db")
        self.db_patch.start()
        database.init_db()
        self.environment = patch.dict(os.environ, {"PRINT_AGENT_TOKEN": "test-agent-token"})
        self.environment.start()
        self.client = self.staff_client()

    def tearDown(self):
        self.environment.stop()
        self.db_patch.stop()
        self.directory.cleanup()

    def staff_client(self, station="station-1"):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session.update(role="station", station_id=station, csrf_token="test-csrf")
        client.environ_base["HTTP_X_CSRF_TOKEN"] = "test-csrf"
        return client

    def sql(self, statement, values=()):
        conn = database.get_connection()
        try:
            rows = conn.execute(statement, values).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    def create_order(self, destination="simple_bluetooth", client=None):
        body = {"itens": [{"id": 1, "q": 2}], "obs": "Sem molho"}
        if destination is not None:
            body["impressao_destino"] = destination
        response = (client or self.client).post("/api/pedidos", json=body)
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["pedido"]

    def prepare(self, order, destination=None, client=None):
        return (client or self.client).post(
            f"/api/pedidos/{order['id']}/impressao/preparar",
            json={"destino": destination or order["impressao_destino"]},
        )

    def next_job(self):
        return app_module.app.test_client().get(
            "/api/print-agent/jobs/next?station_id=station-1",
            headers={"X-Print-Agent-Token": "test-agent-token", "X-Print-Agent-Id": "test-esp32"},
        )

    def snapshot(self):
        conn = database.get_connection()
        try:
            return list(conn.iterdump())
        finally:
            conn.close()

    def test_default_destination_prints_directly_without_queue(self):
        order = self.create_order(destination=None)
        self.assertEqual(order["impressao_destino"], "simple_bluetooth")
        self.assertEqual(self.sql("SELECT estoque FROM produtos WHERE id=1")[0]["estoque"], 28)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM print_jobs")[0]["n"], 0)
        self.assertEqual(self.next_job().status_code, 410)

    def test_each_direct_destination_is_persisted_without_queue_or_extra_stock_changes(self):
        for destination in ("simple_bluetooth", "web_bluetooth", "airprint"):
            with self.subTest(destination=destination):
                stock = self.sql("SELECT estoque FROM produtos WHERE id=1")[0]["estoque"]
                order = self.create_order(destination)
                self.assertEqual(order["impressao_destino"], destination)
                self.assertEqual(order["impressao_status"], "pendente")
                self.assertEqual(self.sql("SELECT estoque FROM produtos WHERE id=1")[0]["estoque"], stock - 2)
                self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM print_jobs")[0]["n"], 0)
                before = self.snapshot()
                for _ in range(2):
                    prepared = self.prepare(order)
                    self.assertEqual(prepared.status_code, 200)
                    self.assertEqual(prepared.get_json()["pedido"], order)
                self.assertEqual(self.snapshot(), before)
        listed = self.client.get("/api/dados").get_json()["pedidos"]
        self.assertEqual({order["impressao_destino"] for order in listed}, {"simple_bluetooth", "web_bluetooth", "airprint"})

    def test_invalid_destination_does_not_create_order_or_decrement_stock(self):
        before = self.snapshot()
        for destination in ("other", "", None, [], {}, True):
            with self.subTest(destination=destination):
                response = self.client.post(
                    "/api/pedidos", json={"itens": [{"id": 1, "q": 1}], "impressao_destino": destination},
                )
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_order_validation_still_rolls_back_for_direct_destination(self):
        before = self.snapshot()
        response = self.client.post(
            "/api/pedidos", json={"itens": [{"id": 1, "q": 100}], "impressao_destino": "simple_bluetooth"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.snapshot(), before)

    def test_prepare_requires_session_csrf_and_owner_station(self):
        order = self.create_order()
        anonymous = app_module.app.test_client()
        self.assertEqual(self.prepare(order, client=anonymous).status_code, 401)
        missing_csrf = self.staff_client()
        missing_csrf.environ_base.pop("HTTP_X_CSRF_TOKEN")
        self.assertEqual(self.prepare(order, client=missing_csrf).status_code, 403)
        self.assertEqual(self.prepare(order, client=self.staff_client("station-2")).status_code, 403)
        admin = self.staff_client("station-2")
        with admin.session_transaction() as session:
            session["role"] = "admin"
        own_order = self.create_order("airprint", client=admin)
        self.assertEqual(own_order["estacao_id"], "station-2")
        self.assertEqual(self.prepare(own_order, client=admin).status_code, 200)

    def test_creation_preserves_session_and_csrf_requirements(self):
        body = {"itens": [{"id": 1, "q": 1}], "impressao_destino": "airprint"}
        self.assertEqual(app_module.app.test_client().post("/api/pedidos", json=body).status_code, 401)
        client = self.staff_client()
        client.environ_base.pop("HTTP_X_CSRF_TOKEN")
        self.assertEqual(client.post("/api/pedidos", json=body).status_code, 403)
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM pedidos")[0]["n"], 0)

    def test_prepare_rejects_mismatched_destination_without_mutating_order(self):
        order = self.create_order()
        before = self.snapshot()
        self.assertEqual(self.prepare(order, "airprint").status_code, 409)
        self.assertEqual(self.prepare(order, "web_bluetooth").status_code, 409)
        self.assertEqual(self.snapshot(), before)
        standard = self.create_order("padrao")
        self.assertEqual(self.prepare(standard, "simple_bluetooth").status_code, 200)

    def test_prepare_rejects_cancelled_or_missing_order(self):
        order = self.create_order()
        self.assertEqual(self.client.post(f"/api/pedidos/{order['id']}/cancelar").status_code, 200)
        before = self.snapshot()
        self.assertEqual(self.prepare(order).status_code, 409)
        self.assertEqual(self.prepare({"id": 999, "impressao_destino": "airprint"}).status_code, 404)
        self.assertEqual(self.snapshot(), before)

    def test_prepare_validates_body_and_returns_fresh_server_order(self):
        order = self.create_order()
        url = f"/api/pedidos/{order['id']}/impressao/preparar"
        for body in (None, [], {}, {"destino": []}, {"destino": "padrao"}, {"destino": "invalid"}):
            self.assertEqual(self.client.post(url, json=body).status_code, 400)
        self.sql("UPDATE pedidos SET observacao='Atualizado no servidor' WHERE id=?", (order["id"],))
        prepared = self.prepare(order)
        self.assertEqual(prepared.get_json()["pedido"]["obs"], "Atualizado no servidor")
        self.assertEqual(prepared.get_json()["pedido"]["impressao_status"], "pendente")

    def test_reprint_cannot_create_a_queue_job(self):
        for destination in ("simple_bluetooth", "web_bluetooth", "airprint", "padrao"):
            order = self.create_order(destination)
            before = self.snapshot()
            self.assertEqual(self.client.post(f"/api/pedidos/{order['id']}/reimprimir").status_code, 410)
            self.assertEqual(self.snapshot(), before)

    def test_old_queue_is_inactive_without_deleting_records(self):
        order = self.create_order()
        self.sql("INSERT INTO print_jobs(pedido_id,station_id,payload) VALUES(?,'station-1','{}')", (order["id"],))
        before = self.snapshot()
        self.assertEqual(self.next_job().status_code, 410)
        self.assertEqual(self.snapshot(), before)

    def test_old_default_clients_also_save_without_queue(self):
        order = self.create_order("padrao")
        self.assertEqual(order["impressao_destino"], "simple_bluetooth")
        self.assertEqual(self.sql("SELECT COUNT(*) AS n FROM print_jobs")[0]["n"], 0)


class PrintDestinationMigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "legacy.db"
        self.db_patch = patch.object(database, "DB_PATH", self.path)
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.directory.cleanup()

    def create_legacy_db(self):
        conn = sqlite3.connect(self.path)
        try:
            conn.executescript("""
                CREATE TABLE pedidos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT NOT NULL, numero INTEGER,
                    observacao TEXT DEFAULT '', entregar_junto INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'em_preparo', cancelado INTEGER NOT NULL DEFAULT 0,
                    data_criacao TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    estacao_id TEXT NOT NULL DEFAULT 'station-1',
                    impressao_status TEXT NOT NULL DEFAULT 'pendente', impressao_atualizada_em TEXT
                );
                INSERT INTO pedidos(tipo,observacao) VALUES ('Balcão','Pedido anterior à migração');
            """)
            conn.commit()
        finally:
            conn.close()

    def backups(self):
        return list(self.path.parent.glob("legacy.before-impressao-destino-*.db"))

    def test_fresh_database_has_destination_without_backup(self):
        database.init_db()
        self.assertFalse(self.backups())
        conn = sqlite3.connect(self.path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(pedidos)")}
            self.assertIn("impressao_destino", columns)
        finally:
            conn.close()

    def test_existing_database_is_backed_up_once_before_additive_migration(self):
        self.create_legacy_db()
        database.init_db()
        self.assertEqual(len(self.backups()), 1)
        backup_path = self.backups()[0]
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(backup_path.stat().st_mode), 0o600)
        backup = sqlite3.connect(backup_path)
        try:
            self.assertEqual(backup.execute("PRAGMA quick_check").fetchone()[0], "ok")
            columns = {row[1] for row in backup.execute("PRAGMA table_info(pedidos)")}
            self.assertNotIn("impressao_destino", columns)
            self.assertEqual(backup.execute("SELECT observacao FROM pedidos").fetchone()[0], "Pedido anterior à migração")
        finally:
            backup.close()
        conn = sqlite3.connect(self.path)
        try:
            self.assertEqual(conn.execute("SELECT impressao_destino,observacao FROM pedidos").fetchone(),
                             ("simple_bluetooth", "Pedido anterior à migração"))
        finally:
            conn.close()
        database.init_db()
        self.assertEqual(self.backups(), [backup_path])

    def test_backup_failure_blocks_schema_change(self):
        self.create_legacy_db()
        with patch.object(database, "NamedTemporaryFile", side_effect=OSError("Backup indisponível")):
            with self.assertRaises(OSError):
                database.init_db()
        conn = sqlite3.connect(self.path)
        try:
            self.assertNotIn("impressao_destino", {row[1] for row in conn.execute("PRAGMA table_info(pedidos)")})
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0], 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
