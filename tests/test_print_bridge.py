from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import database
import print_bridge

# Importing app initializes SQLite; keep that initialization away from instance/.
with tempfile.TemporaryDirectory() as import_dir:
    with patch.object(database, "DB_PATH", Path(import_dir) / "import.db"):
        import app as app_module


CODE = "123456789012"
BASE_URL = f"https://bluetoothprinterplus.firebaseio.com/printFromAnywhere/{CODE}"
PRINTER = "AA:BB:CC:DD:EE:01"
OTHER_PRINTER = "AA:BB:CC:DD:EE:02"


def firebase_response(value, etag=None):
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = json.dumps(value).encode("utf-8")
    response.headers = {} if etag is None else {"ETag": etag}
    return response


class PrintBridgeServiceTests(unittest.TestCase):
    def test_large_receipt_keeps_dividers_quantities_and_long_product_names(self):
        separator = "-" * 32
        text = (
            "    D&A LANCHE'S\n    PEDIDO #7\n    15/11/2026  14:16\n"
            + separator + "\n2x Pastel de carne de sol\n   c/ queijo e catupiry\n"
            + separator + "\n    Obrigado!\n"
        )
        lines = print_bridge._large_receipt_lines(text)
        self.assertEqual(sum(line.get("divider", False) for line in lines), 2)
        self.assertTrue(all(len(line["text"]) <= (14 if line["doubleSize"] else 32)
                            for line in lines if "text" in line))
        items = [line["text"] for line in lines if line.get("align") == "left"]
        self.assertTrue(items[0].startswith("2x "))
        self.assertTrue(all(line.startswith("   ") for line in items[1:]))
        self.assertEqual(" ".join(line.strip() for line in items),
                         "2x Pastel de carne de sol c/ queijo e catupiry")


    def test_older_page_prints_misto_with_one_time_in_footer(self):
        separator = "-" * 32
        text = (
            "D&A LANCHE'S\nPEDIDO #7\n16/11/2026  18:38\n18:38\n"
            + separator + "\n2x Pastel de misto\n" + separator + "\nObrigado!\n"
        )
        lines = print_bridge._large_receipt_lines(text)
        self.assertEqual(
            [line["text"] for line in lines if "text" in line],
            ["D&A LANCHE'S", "PEDIDO #7", "2x Misto", "Obrigado!", "16/11/2026 18:38"],
        )
        self.assertTrue(lines[3]["doubleSize"])
        self.assertFalse(lines[0]["doubleSize"])
        self.assertFalse(lines[1]["doubleSize"])

    def test_mistao_keeps_name_and_quantity_on_one_large_line(self):
        separator = "-" * 32
        for name in ("Pastel mistão", "Pastel de mistão", "Pastel mistao", "Mistão"):
            for quantity in (1, 2, 12):
                text = "D&A LANCHE'S\nPEDIDO #7\n" + separator + "\n"
                text += f"{quantity}x {name}\n" + separator + "\n17/11/2026 18:38\n"
                lines = print_bridge._large_receipt_lines(text)
                items = [line for line in lines if line.get("align") == "left"]
                self.assertEqual([line["text"] for line in items], [f"{quantity}x Mistao"])
                self.assertTrue(items[0]["doubleSize"])

    def test_printer_segments_use_ascii_for_mistao_and_accented_names(self):
        separator = "-" * 32
        for name in ("Pastel mistão", "Pastel mistao", "Mistão", "Mistao"):
            text = "D&A LANCHE'S\nPEDIDO #2\n" + separator + "\n2x " + name + "\n" + separator + "\n17/11/2026 18:38\n"
            lines = print_bridge._large_receipt_lines(text)
            self.assertEqual([line["text"] for line in lines if line.get("align") == "left"], ["2x Mistao"])
            self.assertTrue(all(line.get("text", "").isascii() for line in lines))
        text = "D&A LANCHE'S\nPEDIDO #2\n" + separator + "\n1x Pão de queijo\n"
        lines = print_bridge._large_receipt_lines(text)
        self.assertEqual(" ".join(line["text"].strip() for line in lines if line.get("align") == "left"), "1x Pao de queijo")

    def test_many_items_have_one_time_in_the_footer(self):
        separator = "-" * 32
        text = "D&A LANCHE'S\nPEDIDO #7\n18/11/2026 17:16\n" + separator + "\n"
        text += "\n\n".join(f"1x Pastel queijo {index}" for index in range(15))
        text += "\n" + separator + "\n18/11/2026 17:16\n17:16\n"
        lines = print_bridge._large_receipt_lines(text)
        self.assertEqual(sum("17:16" in line.get("text", "") for line in lines), 1)
        self.assertEqual(lines[-1]["text"], "18/11/2026 17:16")
        self.assertEqual(sum("18/11/2026" in line.get("text", "") for line in lines), 1)
        self.assertEqual(sum(line.get("text", "").startswith("1x ") for line in lines), 15)

    def test_legacy_small_tags_never_reach_the_printer(self):
        divider = "-" * 32
        text = (
            "[center][small]D&A LANCHE'S[/small][/center]\n"
            "[small]PEDIDO #115[/small]\n" + divider +
            "\n1x PASTEL FRANGO C/ CATUPIRY\n" + divider +
            "\n[[small]]19/11/2026 11:07[[/small]]\n"
        )
        lines = print_bridge._large_receipt_lines(text)
        rendered = "\n".join(line.get("text", "") for line in lines)
        self.assertNotIn("[", rendered)
        self.assertNotIn("]", rendered)
        self.assertEqual(lines[-1]["text"], "19/11/2026 11:07")

    def setUp(self):
        self.urlopen_patch = patch.object(print_bridge, "urlopen")
        self.urlopen = self.urlopen_patch.start()
        self.addCleanup(self.urlopen_patch.stop)

    def configure_responses(self, session=None, previous=None, etag='"test-etag"'):
        if session is None:
            session = {"availableDevices": {PRINTER: "Synthetic printer"}}
        self.urlopen.side_effect = [
            firebase_response(session),
            firebase_response(previous, etag),
            firebase_response({"status": "pending"}),
        ]

    def requests(self):
        return [call.args[0] for call in self.urlopen.call_args_list]

    def assert_no_put(self):
        self.assertTrue(all(request.get_method() != "PUT" for request in self.requests()))

    def test_fixed_rest_urls_exact_etag_and_native_large_text_payload(self):
        etag = '"opaque+/etag=="'
        self.configure_responses(etag=etag)
        with patch.object(print_bridge.time, "time", return_value=1234.567):
            print_bridge.send_to_android(CODE, "PEDIDO #7\n1x Pastel")
        requests = self.requests()
        self.assertEqual([request.get_method() for request in requests], ["GET", "GET", "PUT"])
        self.assertEqual([request.full_url for request in requests],
                         [BASE_URL + ".json", BASE_URL + "/job.json", BASE_URL + "/job.json"])
        headers = [{name.lower(): value for name, value in request.header_items()} for request in requests]
        self.assertEqual(headers[1]["x-firebase-etag"], "true")
        self.assertEqual(headers[2]["if-match"], etag)
        self.assertEqual(headers[2]["content-type"], "application/json")
        self.assertNotIn("authorization", headers[2])
        self.assertEqual(json.loads(requests[2].data), {
            "status": "pending", "createdAt": 1234567,
            "richText": [
                {"text": "PEDIDO #7", "align": "center", "bold": True, "underline": False, "doubleSize": False},
                {"text": "1x Pastel", "align": "center", "bold": False, "underline": False, "doubleSize": False},
            ],
            "strictMode": False, "targetDevice": PRINTER,
        })
        self.assertTrue(all(call.kwargs == {"timeout": 8} for call in self.urlopen.call_args_list))

    def test_connected_default_and_only_available_printer_are_selected(self):
        sessions = [
            {"availableDevices": {PRINTER: "One", OTHER_PRINTER: "Two"},
             "connectedDeviceAddress": PRINTER, "defaultDevice": OTHER_PRINTER},
            {"availableDevices": {PRINTER: "One", OTHER_PRINTER: "Two"}, "defaultDevice": PRINTER},
            {"availableDevices": {PRINTER: "One", OTHER_PRINTER: "Two"},
             "connectedDeviceAddress": "not-available", "defaultDevice": PRINTER},
            {"availableDevices": {PRINTER: "One"}, "connectedDeviceAddress": "not-available"},
        ]
        for session in sessions:
            with self.subTest(session=session):
                self.urlopen.reset_mock()
                self.configure_responses(session)
                print_bridge.send_to_android(CODE, "Synthetic ticket")
                self.assertEqual(json.loads(self.requests()[-1].data)["targetDevice"], PRINTER)

    def test_missing_session_is_rejected_before_any_write(self):
        for session in (None, [], "expired"):
            with self.subTest(session=session):
                self.urlopen.reset_mock()
                self.urlopen.side_effect = [firebase_response(session)]
                with self.assertRaises(print_bridge.PrintBridgeError):
                    print_bridge.send_to_android(CODE, "Synthetic ticket")
                self.assertEqual(self.urlopen.call_count, 1)
                self.assert_no_put()

    def test_no_printer_or_ambiguous_printers_are_rejected_without_put(self):
        for session in (
            {}, {"availableDevices": {}}, {"availableDevices": []},
            {"availableDevices": {PRINTER: "One", OTHER_PRINTER: "Two"}},
        ):
            with self.subTest(session=session):
                self.urlopen.reset_mock()
                self.configure_responses(session)
                with self.assertRaises(print_bridge.PrintBridgeError):
                    print_bridge.send_to_android(CODE, "Synthetic ticket")
                self.assert_no_put()

    def test_pending_printing_and_unknown_job_state_are_never_overwritten(self):
        for previous in ({"status": "pending"}, {"status": "printing"},
                         {"status": "unknown"}, {}, "invalid"):
            with self.subTest(previous=previous):
                self.urlopen.reset_mock()
                self.configure_responses(previous=previous)
                with self.assertRaises(print_bridge.PrintBridgeError):
                    print_bridge.send_to_android(CODE, "Synthetic ticket")
                self.assertEqual(self.urlopen.call_count, 2)
                self.assert_no_put()

    def test_completed_or_failed_job_allows_a_new_explicit_send(self):
        for status in ("printed", "error"):
            with self.subTest(status=status):
                self.urlopen.reset_mock()
                self.configure_responses(previous={"status": status})
                print_bridge.send_to_android(CODE, "Synthetic ticket")
                self.assertEqual(self.requests()[-1].get_method(), "PUT")
                self.assertEqual(self.urlopen.call_count, 3)

    def test_missing_etag_fails_closed_without_put(self):
        self.configure_responses(etag=None)
        with self.assertRaises(print_bridge.PrintBridgeError):
            print_bridge.send_to_android(CODE, "Synthetic ticket")
        self.assertEqual(self.urlopen.call_count, 2)
        self.assert_no_put()

    def test_conditional_write_conflict_is_reported_without_retry(self):
        self.configure_responses()
        self.urlopen.side_effect = [
            firebase_response({"availableDevices": {PRINTER: "One"}}),
            firebase_response(None, '"old-etag"'),
            HTTPError(BASE_URL + "/job.json", 412, "Precondition Failed", {}, BytesIO(b"{}")),
        ]
        with self.assertRaisesRegex(print_bridge.PrintBridgeError, "Outra impressão"):
            print_bridge.send_to_android(CODE, "Synthetic ticket")
        self.assertEqual(self.urlopen.call_count, 3)
        self.assertEqual([request.get_method() for request in self.requests()].count("PUT"), 1)

    def test_put_timeout_or_network_error_is_uncertain_and_never_retried(self):
        for error in (TimeoutError("Synthetic timeout"), URLError("Synthetic network failure")):
            with self.subTest(error=type(error).__name__):
                self.urlopen.reset_mock()
                self.urlopen.side_effect = [
                    firebase_response({"availableDevices": {PRINTER: "One"}}),
                    firebase_response(None, '"old-etag"'), error,
                ]
                with self.assertRaisesRegex(print_bridge.PrintBridgeError, "incerta"):
                    print_bridge.send_to_android(CODE, "Synthetic ticket")
                self.assertEqual(self.urlopen.call_count, 3)
                self.assertEqual([request.get_method() for request in self.requests()].count("PUT"), 1)

    def test_invalid_non_ascii_or_path_like_codes_do_not_reach_network(self):
        for code in (None, 123456789012, "", "12345678901", "1234567890123",
                     "１２３４５６７８９０１２", "١٢٣٤٥٦٧٨٩٠١٢", "123456789/12"):
            with self.subTest(code=code):
                with self.assertRaises(print_bridge.PrintBridgeError):
                    print_bridge.send_to_android(code, "Synthetic ticket")
        self.urlopen.assert_not_called()


class PrintBridgeEndpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, "DB_PATH", Path(self.directory.name) / "test.db")
        self.db_patch.start()
        database.init_db()
        self.sender_patch = patch.object(app_module, "send_to_android")
        self.sender = self.sender_patch.start()
        self.client = self.staff_client()
        self.order = self.create_order()

    def tearDown(self):
        self.sender_patch.stop()
        self.db_patch.stop()
        self.directory.cleanup()

    def staff_client(self, station="station-1", role="station"):
        client = app_module.app.test_client()
        with client.session_transaction() as session:
            session.update(role=role, station_id=station, csrf_token="test-csrf")
        client.environ_base["HTTP_X_CSRF_TOKEN"] = "test-csrf"
        return client

    def create_order(self, destination="simple_bluetooth", client=None):
        response = (client or self.client).post("/api/pedidos", json={
            "impressao_destino": destination, "itens": [{"id": 1, "q": 2}],
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["pedido"]

    def send(self, body=None, client=None, order=None):
        order = order or self.order
        return (client or self.client).post(
            f"/api/pedidos/{order['id']}/impressao/android",
            json=body if body is not None else {"code": CODE, "text": "PEDIDO #1\n1x Pastel"},
        )

    def snapshot(self):
        conn = database.get_connection()
        try:
            return list(conn.iterdump())
        finally:
            conn.close()

    def test_send_reports_acceptance_without_mutating_stock_queue_or_pending_order(self):
        before = self.snapshot()
        response = self.send()
        self.assertEqual(response.status_code, 202, response.get_json())
        self.assertEqual(response.get_json(), {"status": "enviado"})
        self.sender.assert_called_once_with(CODE, "PEDIDO #1\n1x Pastel")
        self.assertEqual(self.snapshot(), before)
        data = self.client.get("/api/dados").get_json()
        saved = next(order for order in data["pedidos"] if order["id"] == self.order["id"])
        self.assertEqual(saved["impressao_status"], "pendente")
        self.assertEqual(next(product for product in data["produtos"] if product["id"] == 1)["e"], 28)

    def test_auth_csrf_role_and_owner_checks_prevent_external_send(self):
        anonymous = app_module.app.test_client()
        missing_csrf = self.staff_client()
        missing_csrf.environ_base.pop("HTTP_X_CSRF_TOKEN")
        wrong_csrf = self.staff_client()
        wrong_csrf.environ_base["HTTP_X_CSRF_TOKEN"] = "wrong-csrf"
        for client, status in (
            (anonymous, 401), (missing_csrf, 403), (wrong_csrf, 403),
            (self.staff_client("station-2"), 403),
            (self.staff_client("station-2", "admin"), 403),
            (self.staff_client(role="viewer"), 403),
        ):
            with self.subTest(status=status):
                self.assertEqual(self.send(client=client).status_code, status)
        self.sender.assert_not_called()

    def test_admin_can_send_only_its_own_station_order(self):
        admin = self.staff_client("station-2", "admin")
        order = self.create_order(client=admin)
        self.assertEqual(self.send(client=admin, order=order).status_code, 202)
        self.sender.assert_called_once()

    def test_cancelled_web_bluetooth_and_missing_orders_are_rejected_without_send(self):
        self.assertEqual(self.client.post(f"/api/pedidos/{self.order['id']}/cancelar").status_code, 200)
        web_order = self.create_order("web_bluetooth")
        before = self.snapshot()
        self.assertEqual(self.send().status_code, 409)
        self.assertEqual(self.send(order=web_order).status_code, 409)
        self.assertEqual(self.send(order={"id": 999999}).status_code, 404)
        self.sender.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_malformed_json_and_wrong_body_types_are_rejected(self):
        url = f"/api/pedidos/{self.order['id']}/impressao/android"
        for body in (None, [], "text", {}, {"code": CODE}, {"code": CODE, "text": 5}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(url, json=body).status_code, 400)
        self.assertEqual(self.client.post(url, data="{", content_type="application/json").status_code, 400)
        self.sender.assert_not_called()

    def test_code_requires_exactly_twelve_ascii_digits(self):
        for code in (None, 123456789012, "12345678901", "1234567890123",
                     "１２３４５６７８９０１２", "١٢٣٤٥٦٧٨٩٠١٢", "1234 5678 9012", "123456789/12"):
            with self.subTest(code=code):
                self.assertEqual(self.send({"code": code, "text": "Synthetic ticket"}).status_code, 400)
        self.sender.assert_not_called()

    def test_four_thousand_character_limit_and_line_breaks(self):
        self.assertEqual(self.send({"code": CODE, "text": "x" * 4000}).status_code, 202)
        self.sender.assert_called_once_with(CODE, "x" * 4000)
        self.sender.reset_mock()
        for text in ("", "x" * 4001):
            self.assertEqual(self.send({"code": CODE, "text": text}).status_code, 400)
        self.sender.assert_not_called()
        text = "PEDIDO\r\n1x Pão de queijo"
        self.assertEqual(self.send({"code": CODE, "text": text}).status_code, 202)
        self.sender.assert_called_once_with(CODE, text)

    def test_control_characters_cannot_reach_the_android_printer(self):
        before = self.snapshot()
        for codepoint in (*range(10), 11, 12, *range(14, 32), 127):
            with self.subTest(codepoint=codepoint):
                self.assertEqual(self.send({"code": CODE, "text": "Ticket" + chr(codepoint)}).status_code, 400)
        self.sender.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_network_failure_returns_error_without_retry_or_database_writes(self):
        before = self.snapshot()
        self.sender.side_effect = print_bridge.PrintBridgeError("Resposta incerta. Confira a impressora.")
        response = self.send()
        self.assertEqual(response.status_code, 502)
        self.assertIn("incerta", response.get_json()["erro"])
        self.sender.assert_called_once()
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
