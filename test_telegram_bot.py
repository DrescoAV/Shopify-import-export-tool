import unittest

from telegram_bot import (
    TelegramBotService,
    parse_allowed_chat_ids,
    parse_telegram_command,
)


class ParseTelegramCommandTests(unittest.TestCase):
    def test_returns_none_for_plain_text(self):
        self.assertIsNone(parse_telegram_command("hello there"))

    def test_parses_command_and_args(self):
        command = parse_telegram_command("/stock ABC-123 25")
        self.assertIsNotNone(command)
        self.assertEqual(command.name, "/stock")
        self.assertEqual(command.args, ["ABC-123", "25"])

    def test_removes_bot_suffix(self):
        command = parse_telegram_command("/price@my_bot ABC-123 19.99")
        self.assertIsNotNone(command)
        self.assertEqual(command.name, "/price")
        self.assertEqual(command.args, ["ABC-123", "19.99"])


class ParseAllowedChatIdsTests(unittest.TestCase):
    def test_empty_value_returns_empty_set(self):
        self.assertEqual(parse_allowed_chat_ids(""), set())

    def test_parses_comma_separated_ids(self):
        self.assertEqual(parse_allowed_chat_ids("123, 456"), {123, 456})


class TelegramBotServiceTests(unittest.TestCase):
    def test_stock_command_calls_shopify_client(self):
        calls = []

        class FakeClient:
            def update_stock(self, *, sku, available):
                calls.append((sku, available))
                return {"sku": sku, "available": available, "on_hand": available}

        bot = TelegramBotService(
            token="token",
            allowed_chat_ids={1},
            create_shopify_client=lambda: FakeClient(),
            parse_price=lambda value: value,
            list_products=lambda: [{"sku": "ABC-123", "product_name": "Product", "price": "10.00"}],
        )

        response = bot._execute_command(parse_telegram_command("/stock ABC-123 25"))

        self.assertEqual(calls, [("ABC-123", 25)])
        self.assertIn("Stock actualizat.", response.text)

    def test_price_command_validates_usage(self):
        bot = TelegramBotService(
            token="token",
            allowed_chat_ids={1},
            create_shopify_client=lambda: None,
            parse_price=lambda value: value,
            list_products=lambda: [],
        )

        response = bot._execute_command(parse_telegram_command("/price ONLYSKU"))
        self.assertEqual(response.text, "Eroare de input: Foloseste: /price SKU PRET")

    def test_products_command_returns_messages(self):
        bot = TelegramBotService(
            token="token",
            allowed_chat_ids={1},
            create_shopify_client=lambda: None,
            parse_price=lambda value: value,
            list_products=lambda: [
                {
                    "sku": "ABC-123",
                    "product_name": "Alpha",
                    "price": "10.00",
                    "product_url": "https://example.com/products/alpha",
                },
                {
                    "sku": "XYZ-789",
                    "product_name": "Beta",
                    "price": "12.50",
                    "product_url": "https://example.com/products/beta",
                },
            ],
        )

        response = bot._execute_command(parse_telegram_command("/products"))

        self.assertEqual(response.text, "Lista produselor. Total randuri exportate: 2")
        self.assertIsNotNone(response.extra_messages)
        self.assertEqual(len(response.extra_messages), 1)
        self.assertEqual(
            response.extra_messages[0].text,
            (
                "1. ABC-123 | <a href=\"https://example.com/products/alpha\">Alpha</a> | 10.00\n"
                "2. XYZ-789 | <a href=\"https://example.com/products/beta\">Beta</a> | 12.50"
            ),
        )
        self.assertEqual(response.extra_messages[0].parse_mode, "HTML")

    def test_products_command_returns_empty_message_when_no_products(self):
        bot = TelegramBotService(
            token="token",
            allowed_chat_ids={1},
            create_shopify_client=lambda: None,
            parse_price=lambda value: value,
            list_products=lambda: [],
        )

        response = bot._execute_command(parse_telegram_command("/products"))

        self.assertEqual(response.text, "Nu am gasit produse exportabile.")
        self.assertIsNone(response.extra_messages)


if __name__ == "__main__":
    unittest.main()
