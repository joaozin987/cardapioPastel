import tempfile
import unittest
import sqlite3
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import database
from PIL import Image
import app as app_module

app = app_module.app


class DatabaseTests(unittest.TestCase):
    def test_admin_password_takes_precedence_over_station_pin(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_PASSWORD": "chosen-admin-password",
                "STATION_2_PIN": "legacy-station-pin",
                "ADMIN_PIN": "legacy-admin-pin",
            },
            clear=True,
        ):
            profiles = app_module.configured_profiles()

        self.assertEqual(profiles["admin"][2], "chosen-admin-password")

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db_path_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        database.init_db()
        self.client = app.test_client()
        self.environment_patch = patch.dict(
            os.environ,
            {
                "ADMIN_PIN": "test-admin-pin",
                "EMPLOYEE_PIN": "test-employee-pin",
            },
        )
        self.environment_patch.start()
        self.profiles_patch = patch.object(
            app_module,
            "PROFILES",
            {
                "employee": ("station-1", "Funcionário", "test-employee-pin", "station"),
                "admin": ("station-2", "Administrador", "test-admin-pin", "admin"),
            },
        )
        self.profiles_patch.start()
        self.login("employee", "test-employee-pin")

    def tearDown(self):
        self.profiles_patch.stop()
        self.environment_patch.stop()
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def login(self, account, credential):
        token = self.client.get("/api/auth/session").get_json()["csrf_token"]
        self.client.environ_base["HTTP_X_CSRF_TOKEN"] = token
        response = self.client.post(
            "/api/auth/login",
            json={"account": account, "credential": credential},
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.client.environ_base["HTTP_X_CSRF_TOKEN"] = response.get_json()["csrf_token"]

    def login_admin(self):
        self.login("admin", "test-admin-pin")

    def test_init_db_seeds_catalog_once_and_preserves_stock(self):
        conn = database.get_connection()
        try:
            product_count = conn.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
            conn.execute("UPDATE produtos SET estoque=7 WHERE id=1")
            conn.execute("UPDATE produtos SET preco=12 WHERE nome='Pizza brotinho de calabresa'")
            conn.commit()
        finally:
            conn.close()

        database.init_db()

        conn = database.get_connection()
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM produtos").fetchone()[0], product_count)
            self.assertEqual(conn.execute("SELECT estoque FROM produtos WHERE id=1").fetchone()[0], 7)
            self.assertEqual(
                conn.execute(
                    "SELECT preco FROM produtos WHERE nome='Pizza brotinho de calabresa'"
                ).fetchone()[0],
                12,
            )
        finally:
            conn.close()

    def test_requested_catalog_is_seeded_with_optional_prices_and_pizzas_at_ten(self):
        response = self.client.get("/api/dados")
        self.assertEqual(response.status_code, 200)
        products = response.get_json()["produtos"]
        by_name = {product["n"]: product for product in products}

        self.assertEqual(len(products), 24)
        self.assertTrue(all(product["updated"] for product in products))
        self.assertEqual(by_name["Pizza brotinho de calabresa"]["p"], 10)
        self.assertEqual(by_name["Pizza brotinho de mussarela"]["p"], 10)
        self.assertEqual(by_name["Pizza brotinho de frango com catupiry"]["p"], 10)
        for name in (
            "Pastel mistão",
            "Pastel de frango",
            "Pastel de carne",
            "Coxinha de frango com catupiry",
            "Coxinha de costela",
            "Coxinha de frango com bacon",
            "Caldo 400 ml",
            "Caldo 500 ml",
            "Caldo 770 ml",
            "Lasanha de frango",
            "Lasanha de carne",
        ):
            self.assertIsNone(by_name[name]["p"])

    def test_product_without_price_cannot_be_ordered_until_price_is_set(self):
        self.login_admin()
        response = self.client.post(
            "/api/produtos",
            json={"n": "Produto de teste", "c": "Teste", "p": None, "e": None, "on": True},
        )
        self.assertEqual(response.status_code, 200)
        product = response.get_json()["produto"]
        self.assertIsNone(product["p"])

        self.login("employee", "test-employee-pin")
        response = self.client.post(
            "/api/pedidos",
            json={"itens": [{"id": product["id"], "q": 1}]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Defina o preço", response.get_json()["erro"])

        self.login_admin()
        response = self.client.put(
            "/api/produtos",
            json={"id": product["id"], "n": product["n"], "c": product["c"], "p": 9, "on": True},
        )
        self.assertEqual(response.status_code, 200)

        self.login("employee", "test-employee-pin")
        response = self.client.post(
            "/api/pedidos",
            json={"itens": [{"id": product["id"], "q": 1}]},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["pedido"]["itens"][0]["p"], 9)

    def test_product_list_reflects_edits_immediately(self):
        self.login_admin()
        products = self.client.get("/api/produtos").get_json()["produtos"]
        product = next(item for item in products if item["n"] == "Pastel de queijo")

        response = self.client.put(
            "/api/produtos",
            json={
                "id": product["id"],
                "n": "Pastel de queijo atualizado",
                "c": product["c"],
                "d": "Descrição atualizada",
                "p": 11,
                "e": product["e"],
                "on": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        updated = response.get_json()["produto"]
        self.assertEqual(updated["n"], "Pastel de queijo atualizado")
        self.assertEqual(updated["p"], 11)

        listed = self.client.get("/api/produtos").get_json()["produtos"]
        updated_from_list = next(item for item in listed if item["id"] == product["id"])
        self.assertEqual(updated_from_list["n"], "Pastel de queijo atualizado")
        self.assertEqual(updated_from_list["p"], 11)

    def test_product_list_moves_new_and_edited_products_to_the_end(self):
        self.login_admin()
        initial = self.client.get("/api/produtos").get_json()["produtos"]
        first_product = initial[0]

        response = self.client.post(
            "/api/produtos",
            json={"n": "Produto recente", "c": "Teste", "p": 5, "on": True},
        )
        self.assertEqual(response.status_code, 200)
        new_product_id = response.get_json()["produto"]["id"]
        after_create = self.client.get("/api/produtos").get_json()["produtos"]
        self.assertEqual(after_create[-1]["id"], new_product_id)

        response = self.client.put(
            "/api/produtos",
            json={
                "id": first_product["id"],
                "n": first_product["n"],
                "c": first_product["c"],
                "d": first_product["d"],
                "p": first_product["p"],
                "e": first_product["e"],
                "on": first_product["on"],
            },
        )
        self.assertEqual(response.status_code, 200)
        after_edit = self.client.get("/api/produtos").get_json()["produtos"]
        self.assertEqual(after_edit[-1]["id"], first_product["id"])

    def test_product_image_is_cropped_optimized_and_can_be_removed(self):
        self.login_admin()
        product = self.client.get("/api/dados").get_json()["produtos"][0]
        source = BytesIO()
        Image.new("RGB", (900, 600), color="orange").save(source, format="PNG")
        source.seek(0)

        response = self.client.put(
            "/api/produtos",
            data={
                "id": str(product["id"]),
                "n": product["n"],
                "c": product["c"],
                "d": product["d"],
                "p": str(product["p"]),
                "e": str(product["e"]),
                "on": "false",
                "image": (source, "pastel.png"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        updated = response.get_json()["produto"]
        self.assertIsNotNone(updated["img"])
        self.assertFalse(updated["on"])
        image_response = self.client.get(updated["img"])
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.content_type, "image/jpeg")
        self.assertLessEqual(len(image_response.data), 200 * 1024)
        with Image.open(BytesIO(image_response.data)) as saved_image:
            self.assertEqual(saved_image.size, (600, 600))
        image_response.close()

        response = self.client.put(
            "/api/produtos",
            json={
                "id": product["id"],
                "n": product["n"],
                "c": product["c"],
                "d": product["d"],
                "p": product["p"],
                "e": product["e"],
                "on": True,
            },
        )
        self.assertEqual(response.get_json()["produto"]["img"], updated["img"])

        response = self.client.put(
            "/api/produtos",
            data={
                "id": str(product["id"]),
                "n": product["n"],
                "c": product["c"],
                "d": product["d"],
                "p": str(product["p"]),
                "e": str(product["e"]),
                "on": "true",
                "remove_image": "true",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json()["produto"]["img"])
        self.assertEqual(self.client.get(updated["img"]).status_code, 404)

    def test_product_image_upload_rejects_non_image_files(self):
        self.login_admin()
        product = self.client.get("/api/dados").get_json()["produtos"][0]
        response = self.client.put(
            "/api/produtos",
            data={
                "id": str(product["id"]),
                "n": product["n"],
                "c": product["c"],
                "p": str(product["p"]),
                "e": str(product["e"]),
                "on": "true",
                "image": (BytesIO(b"not an image"), "not-image.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("imagem válida", response.get_json()["erro"])

    def test_existing_database_schema_gets_optional_price_column(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        with patch.object(database, "DB_PATH", legacy_path):
            conn = sqlite3.connect(legacy_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE categorias (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome TEXT NOT NULL UNIQUE
                    );
                    CREATE TABLE produtos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        categoria_id INTEGER NOT NULL,
                        nome TEXT NOT NULL,
                        descricao TEXT DEFAULT '',
                        preco REAL NOT NULL CHECK(preco >= 0),
                        estoque INTEGER NULL CHECK(estoque IS NULL OR estoque >= 0),
                        ativo INTEGER NOT NULL DEFAULT 1,
                        FOREIGN KEY(categoria_id) REFERENCES categorias(id)
                    );
                    CREATE TABLE pedidos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tipo TEXT NOT NULL,
                        numero INTEGER NULL,
                        observacao TEXT DEFAULT '',
                        entregar_junto INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'em_preparo',
                        cancelado INTEGER NOT NULL DEFAULT 0,
                        data_criacao TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                    );
                    INSERT INTO categorias(nome) VALUES ('Pastéis');
                    INSERT INTO produtos(categoria_id,nome,descricao,preco,estoque,ativo)
                    VALUES (1,'Pastel antigo','',9,30,1);
                    INSERT INTO pedidos(tipo,numero) VALUES ('Balcão',NULL);
                    """
                )
                conn.commit()
            finally:
                conn.close()

            database.init_db()

            conn = database.get_connection()
            try:
                columns = {row["name"] for row in conn.execute("PRAGMA table_info(produtos)")}
                self.assertIn("preco_definido", columns)
                self.assertIn("imagem", columns)
                self.assertIn("atualizado_em", columns)
                order_columns = {
                    row["name"] for row in conn.execute("PRAGMA table_info(pedidos)")
                }
                self.assertIn("estacao_id", order_columns)
                self.assertIn("impressao_status", order_columns)
                migrated_order = conn.execute(
                    "SELECT estacao_id,impressao_status FROM pedidos WHERE id=1"
                ).fetchone()
                self.assertEqual(migrated_order["estacao_id"], "station-1")
                self.assertEqual(migrated_order["impressao_status"], "pendente")
                self.assertEqual(
                    conn.execute(
                        "SELECT preco_definido FROM produtos WHERE nome='Pastel antigo'"
                    ).fetchone()[0],
                    1,
                )
            finally:
                conn.close()

    def test_order_api_saves_order_decrements_stock_and_cancel_restores_it(self):
        response = self.client.get("/api/dados")
        self.assertEqual(response.status_code, 200)
        products = response.get_json()["produtos"]
        product = products[0]
        initial_stock = product["e"]

        response = self.client.post(
            "/api/pedidos",
            json={"itens": [{"id": product["id"], "q": 2}]},
        )

        self.assertEqual(response.status_code, 201)
        order = response.get_json()["pedido"]
        self.assertEqual(order["itens"][0]["q"], 2)
        self.assertEqual(order["itens"][0]["p"], product["p"])
        self.assertEqual(order["estacao_id"], "station-1")

        updated_product = next(
            item for item in self.client.get("/api/dados").get_json()["produtos"]
            if item["id"] == product["id"]
        )
        self.assertEqual(updated_product["e"], initial_stock - 2)

        response = self.client.post(f"/api/pedidos/{order['id']}/cancelar")
        self.assertEqual(response.status_code, 200)
        restored_product = next(
            item for item in self.client.get("/api/dados").get_json()["produtos"]
            if item["id"] == product["id"]
        )
        self.assertEqual(restored_product["e"], initial_stock)

    def test_invalid_order_does_not_change_stock_or_create_order(self):
        product = self.client.get("/api/dados").get_json()["produtos"][0]
        response = self.client.post(
            "/api/pedidos",
            json={"itens": [{"id": product["id"], "q": product["e"] + 1}]},
        )

        self.assertEqual(response.status_code, 400)
        data = self.client.get("/api/dados").get_json()
        self.assertEqual(len(data["pedidos"]), 0)
        self.assertEqual(data["produtos"][0]["e"], product["e"])

    def test_station_cannot_edit_products_or_access_admin_summary(self):
        response = self.client.post(
            "/api/produtos",
            json={"n": "Produto bloqueado", "c": "Teste", "p": 5, "on": True},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/admin/resumo").status_code, 403)

    def test_admin_can_access_summary_and_create_orders(self):
        self.login_admin()
        self.assertEqual(self.client.get("/api/admin/resumo").status_code, 200)
        product = self.client.get("/api/dados").get_json()["produtos"][0]
        response = self.client.post(
            "/api/pedidos",
            json={"itens": [{"id": product["id"], "q": 1}]},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["pedido"]["estacao_id"], "station-2")

        order_id = response.get_json()["pedido"]["id"]
        claim = self.client.post(
            f"/api/pedidos/{order_id}/impressao",
            json={"status": "imprimindo"},
        )
        self.assertEqual(claim.status_code, 200)
        printed = self.client.post(
            f"/api/pedidos/{order_id}/impressao",
            json={"status": "impresso"},
        )
        self.assertEqual(printed.status_code, 200)

    def test_only_employee_and_admin_profiles_are_available(self):
        client = app.test_client()
        token = client.get("/api/auth/session").get_json()["csrf_token"]
        for account in ("station1", "station2"):
            response = client.post(
                "/api/auth/login",
                json={"account": account, "credential": "test-employee-pin"},
                headers={"X-CSRF-Token": token},
            )
            self.assertEqual(response.status_code, 401)

    def test_existing_station_sessions_migrate_to_the_two_profiles(self):
        client = app.test_client()
        with client.session_transaction() as browser_session:
            browser_session.update(role="station", station_id="station-2")

        response = client.get("/api/auth/session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["role"], "admin")
        self.assertEqual(response.get_json()["station_id"], "station-2")
        self.assertEqual(response.get_json()["station_name"], "Administrador")

    def test_station_order_is_owned_and_print_state_is_single_start(self):
        product = self.client.get("/api/dados").get_json()["produtos"][0]
        created = self.client.post(
            "/api/pedidos",
            json={"itens": [{"id": product["id"], "q": 1}]},
        )
        self.assertEqual(created.status_code, 201)
        order_id = created.get_json()["pedido"]["id"]

        station_two = app.test_client()
        token = station_two.get("/api/auth/session").get_json()["csrf_token"]
        station_two.environ_base["HTTP_X_CSRF_TOKEN"] = token
        logged_in = station_two.post(
            "/api/auth/login",
            json={"account": "admin", "credential": "test-admin-pin"},
        )
        self.assertEqual(logged_in.status_code, 200)
        wrong_station = station_two.post(
            f"/api/pedidos/{order_id}/impressao",
            json={"status": "imprimindo"},
        )
        self.assertEqual(wrong_station.status_code, 403)

        claim = self.client.post(
            f"/api/pedidos/{order_id}/impressao",
            json={"status": "imprimindo"},
        )
        self.assertEqual(claim.status_code, 200)
        duplicate_claim = self.client.post(
            f"/api/pedidos/{order_id}/impressao",
            json={"status": "imprimindo"},
        )
        self.assertEqual(duplicate_claim.status_code, 409)
        printed = self.client.post(
            f"/api/pedidos/{order_id}/impressao",
            json={"status": "impresso"},
        )
        self.assertEqual(printed.status_code, 200)
        duplicate_result = self.client.post(
            f"/api/pedidos/{order_id}/impressao",
            json={"status": "impresso"},
        )
        self.assertEqual(duplicate_result.status_code, 409)

    def test_unauthenticated_requests_are_rejected(self):
        client = app.test_client()
        self.assertEqual(client.get("/api/dados").status_code, 401)
        self.assertEqual(
            client.post(
                "/api/pedidos",
                json={"itens": [{"id": 1, "q": 1}]},
            ).status_code,
            401,
        )
        login_page = client.get("/api/auth/session")
        response = client.post(
            "/api/auth/login",
            json={"account": "employee", "credential": "wrong"},
            headers={"X-CSRF-Token": login_page.get_json()["csrf_token"]},
        )
        self.assertEqual(response.status_code, 401)

    def test_repeated_login_failures_temporarily_lock_the_account(self):
        client = app.test_client()
        token = client.get("/api/auth/session").get_json()["csrf_token"]
        statuses = [
            client.post(
                "/api/auth/login",
                json={"account": "employee", "credential": "wrong-pin"},
                headers={"X-CSRF-Token": token},
            ).status_code
            for _ in range(5)
        ]
        self.assertEqual(statuses, [401, 401, 401, 401, 429])
        blocked_valid_login = client.post(
            "/api/auth/login",
            json={"account": "employee", "credential": "test-employee-pin"},
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(blocked_valid_login.status_code, 429)


if __name__ == "__main__":
    unittest.main()
