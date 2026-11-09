import unittest

from app import app


class HomeRouteTests(unittest.TestCase):
    def test_home_serves_the_orders_page(self):
        response = app.test_client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        self.assertIn(b"D&amp;A Lanche's", response.data)
        self.assertIn(b"loginAccount", response.data)
        self.assertIn(b"Funcion\xc3\xa1rio", response.data)
        self.assertIn(b'value="employee"', response.data)
        self.assertIn(b'value="admin"', response.data)
        self.assertNotIn(b'value="station1"', response.data)
        self.assertNotIn(b'value="station2"', response.data)
        self.assertNotIn(b"Aparelho 1", response.data)
        self.assertNotIn(b"Aparelho 2", response.data)
        self.assertIn(b"Painel do administrador", response.data)


if __name__ == "__main__":
    unittest.main()
