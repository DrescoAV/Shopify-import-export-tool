import unittest

from shopify_client import ShopifyClient, derive_inventory_targets


class DeriveInventoryTargetsTests(unittest.TestCase):
    def test_available_and_on_hand_are_allowed(self):
        current = {"available": 8, "on_hand": 10, "unavailable": 2}

        result = derive_inventory_targets(
            current_quantities=current,
            requested={"available": 12, "on_hand": 17},
        )

        self.assertEqual(result["available"], 12)
        self.assertEqual(result["on_hand"], 17)
        self.assertEqual(result["unavailable"], 5)

    def test_available_only_keeps_current_on_hand(self):
        current = {"available": 8, "on_hand": 10, "unavailable": 2}

        result = derive_inventory_targets(
            current_quantities=current,
            requested={"available": 9},
        )

        self.assertEqual(result["available"], 9)
        self.assertEqual(result["on_hand"], 10)
        self.assertEqual(result["unavailable"], 1)

    def test_available_only_raises_on_hand_when_needed(self):
        current = {"available": 8, "on_hand": 8, "unavailable": 0}

        result = derive_inventory_targets(
            current_quantities=current,
            requested={"available": 12},
        )

        self.assertEqual(result["available"], 12)
        self.assertEqual(result["on_hand"], 12)
        self.assertEqual(result["unavailable"], 0)

    def test_on_hand_only_keeps_current_available(self):
        current = {"available": 8, "on_hand": 10, "unavailable": 2}

        result = derive_inventory_targets(
            current_quantities=current,
            requested={"on_hand": 15},
        )

        self.assertEqual(result["available"], 8)
        self.assertEqual(result["on_hand"], 15)
        self.assertEqual(result["unavailable"], 7)

    def test_committed_is_not_directly_supported(self):
        current = {"available": 8, "on_hand": 10, "unavailable": 2}

        with self.assertRaises(ValueError):
            derive_inventory_targets(
                current_quantities=current,
                requested={"committed": 4},
            )

    def test_unavailable_is_not_directly_supported(self):
        current = {"available": 8, "on_hand": 10, "unavailable": 2}

        with self.assertRaises(ValueError):
            derive_inventory_targets(
                current_quantities=current,
                requested={"unavailable": 4},
            )


class UpdateStockOrderingTests(unittest.TestCase):
    def test_increasing_available_updates_on_hand_first(self):
        client = ShopifyClient(
            shop_domain="example.myshopify.com",
            access_token="token",
            default_location_id="1",
        )

        calls = []
        snapshots = iter(
            [
                {"available": 8, "on_hand": 8, "unavailable": 0},
                {"available": 8, "on_hand": 12, "unavailable": 4},
                {"available": 12, "on_hand": 12, "unavailable": 0},
                {"available": 12, "on_hand": 12, "unavailable": 0},
            ]
        )

        client.get_inventory_snapshot = lambda **kwargs: next(snapshots)
        client.set_inventory_quantity = lambda **kwargs: calls.append(kwargs)

        result = client.update_stock(
            inventory_item_id=123,
            available=12,
        )

        self.assertEqual(
            [call["name"] for call in calls],
            ["on_hand", "available"],
        )
        self.assertEqual(result["available"], 12)
        self.assertEqual(result["on_hand"], 12)


if __name__ == "__main__":
    unittest.main()
