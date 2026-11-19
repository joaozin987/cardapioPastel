import unittest

from app import app


class HomeRouteTests(unittest.TestCase):
    def test_home_serves_the_orders_page(self):
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("text/html", response.content_type)
        self.assertIn(b"D&amp;A Lanche's", response.data)
        self.assertIn(b"/static/orders-app.js?v=", response.data)
        self.assertNotIn(b"babel-standalone", response.data)
        self.assertNotIn(b"core-js-bundle", response.data)
        script = app.test_client().get("/static/orders-app.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("no-store", script.headers["Cache-Control"])
        self.assertIn(b"loginAccount", script.data)
        self.assertIn(b"Funcion\xc3\xa1rio", script.data)
        self.assertIn(b'value="employee"', script.data)
        self.assertIn(b'value="admin"', script.data)
        self.assertNotIn(b'value="station1"', script.data)
        self.assertNotIn(b'value="station2"', script.data)
        self.assertNotIn(b"Aparelho 1", script.data)
        self.assertNotIn(b"Aparelho 2", script.data)
        self.assertIn(b"Painel do administrador", script.data)


if __name__ == "__main__":
    unittest.main()
