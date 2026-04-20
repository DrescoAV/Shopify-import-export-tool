import re
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import requests


DEFAULT_TIMEOUT = (5, 30)
MAX_LIMIT = 250
QUANTITY_NAMES = [
    "available",
    "committed",
    "incoming",
    "on_hand",
    "reserved",
    "damaged",
    "quality_control",
    "safety_stock",
]


def derive_inventory_targets(
    *,
    current_quantities: dict[str, Any],
    requested: dict[str, Any],
) -> dict[str, int]:
    if requested.get("committed") is not None:
        raise ValueError(
            "Field `committed` cannot be set directly. Shopify derives it from open orders and reservations."
        )

    if requested.get("unavailable") is not None:
        raise ValueError(
            "Field `unavailable` cannot be set directly. Shopify derives it from inventory state and allocations."
        )

    available = requested.get("available")
    on_hand = requested.get("on_hand")

    current_available = int(current_quantities.get("available", 0) or 0)
    current_on_hand = int(current_quantities.get("on_hand", 0) or 0)

    if available is None and on_hand is None:
        raise ValueError(
            "Provide at least one of `available` or `on_hand`."
        )

    if available is not None:
        available = int(available)
    if on_hand is not None:
        on_hand = int(on_hand)

    if available is not None and available < 0:
        raise ValueError("Field `available` must be greater than or equal to 0.")
    if on_hand is not None and on_hand < 0:
        raise ValueError("Field `on_hand` must be greater than or equal to 0.")

    if available is None:
        available = current_available
        if on_hand is not None and on_hand < available:
            available = on_hand

    if on_hand is None:
        on_hand = max(current_on_hand, available)

    if available < 0:
        raise ValueError(
            "Invalid inventory combination. Derived `available` is negative."
        )

    if on_hand < available:
        raise ValueError(
            "Invalid inventory combination. `on_hand` must be greater than or equal to `available`."
        )

    unavailable = max(on_hand - available, 0)

    return {
        "available": int(available),
        "on_hand": int(on_hand),
        "unavailable": int(unavailable),
    }


class ConfigError(Exception):
    pass


class ShopifyAPIError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class ShopifyClient:
    def __init__(
        self,
        *,
        shop_domain: str,
        access_token: str,
        api_version: str = "2026-01",
        default_location_id: str | None = None,
        timeout: tuple[int, int] = DEFAULT_TIMEOUT,
    ) -> None:
        self.shop_domain = self._normalize_shop_domain(shop_domain)
        self.access_token = access_token.strip()
        self.api_version = api_version
        self.default_location_id = (
            str(default_location_id).strip() if default_location_id else None
        )
        self.timeout = timeout
        self.base_url = (
            f"https://{self.shop_domain}/admin/api/{self.api_version}"
        )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Shopify-Access-Token": self.access_token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    @staticmethod
    def _normalize_shop_domain(value: str) -> str:
        cleaned = value.strip()
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            cleaned = urlparse(cleaned).netloc
        cleaned = cleaned.rstrip("/")
        return cleaned

    def _request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        retry_on_throttle: bool = True,
    ) -> requests.Response:
        url = (
            path_or_url
            if path_or_url.startswith("http://") or path_or_url.startswith("https://")
            else f"{self.base_url}{path_or_url}"
        )

        response = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json,
            timeout=self.timeout,
        )

        if response.status_code == 429 and retry_on_throttle:
            time.sleep(1)
            return self._request(
                method,
                path_or_url,
                params=params,
                json=json,
                retry_on_throttle=False,
            )

        if response.ok:
            return response

        details = self._extract_error_payload(response)
        raise ShopifyAPIError(
            f"Shopify API request failed with status {response.status_code}.",
            status_code=response.status_code,
            details=details,
        )

    def _graphql(
        self,
        query: str,
        *,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/graphql.json",
            json={"query": query, "variables": variables or {}},
        )
        payload = self._parse_json(response)
        if payload.get("errors"):
            raise ShopifyAPIError(
                "Shopify GraphQL request failed.",
                status_code=response.status_code,
                details=payload["errors"],
            )
        return payload.get("data", {})

    @staticmethod
    def _extract_error_payload(response: requests.Response) -> Any:
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip()

        if isinstance(payload, dict):
            if "errors" in payload:
                return payload["errors"]
            return payload
        return payload

    @staticmethod
    def _parse_json(response: requests.Response) -> dict[str, Any]:
        try:
            return response.json()
        except ValueError as exc:
            raise ShopifyAPIError(
                "Shopify API returned a non-JSON response.",
                status_code=response.status_code,
                details=response.text.strip(),
            ) from exc

    @staticmethod
    def _extract_next_link(response: requests.Response) -> str | None:
        link_header = response.headers.get("Link", "")
        if not link_header:
            return None

        match = re.search(r"<([^>]+)>;\s*rel=\"next\"", link_header)
        return match.group(1) if match else None

    def iter_products(
        self,
        *,
        fields: list[str] | None = None,
        limit: int = MAX_LIMIT,
    ):
        params: dict[str, Any] | None = {"limit": min(limit, MAX_LIMIT)}
        if fields:
            params["fields"] = ",".join(fields)

        next_url: str | None = "/products.json"

        while next_url:
            response = self._request("GET", next_url, params=params)
            payload = self._parse_json(response)

            for product in payload.get("products", []):
                yield product

            next_url = self._extract_next_link(response)
            params = None

    def get_products_for_export(self) -> list[dict[str, Any]]:
        fields = [
            "id",
            "title",
            "handle",
            "vendor",
            "product_type",
            "image",
            "images",
            "variants",
        ]
        return list(self.iter_products(fields=fields))

    def find_variant_by_sku(self, sku: str) -> dict[str, Any]:
        target = sku.strip()
        if not target:
            raise ValueError("SKU cannot be empty.")

        fields = [
            "id",
            "title",
            "handle",
            "vendor",
            "product_type",
            "image",
            "images",
            "variants",
        ]
        for product in self.iter_products(fields=fields):
            for variant in product.get("variants", []):
                if (variant.get("sku") or "").strip() == target:
                    return {"product": product, "variant": variant}

        raise ShopifyAPIError(
            f"Variant not found for SKU `{target}`.",
            status_code=404,
            details={"sku": target},
        )

    def get_variant(self, variant_id: str | int) -> dict[str, Any]:
        response = self._request("GET", f"/variants/{variant_id}.json")
        payload = self._parse_json(response)
        variant = payload.get("variant")
        if not variant:
            raise ShopifyAPIError(
                "Variant lookup succeeded but response did not include `variant`.",
                status_code=response.status_code,
                details=payload,
            )
        return variant

    def update_variant_price(self, *, variant_id: str | int, price: str) -> dict[str, Any]:
        body = {"variant": {"id": int(variant_id), "price": price}}
        response = self._request("PUT", f"/variants/{variant_id}.json", json=body)
        payload = self._parse_json(response)
        return payload.get("variant", payload)

    def update_price(
        self,
        *,
        price: str,
        sku: str | None = None,
        variant_id: str | int | None = None,
    ) -> dict[str, Any]:
        resolved_variant: dict[str, Any]

        if variant_id:
            resolved_variant = self.get_variant(variant_id)
        elif sku:
            resolved_variant = self.find_variant_by_sku(sku)["variant"]
        else:
            raise ValueError("Provide `sku` or `variant_id` for price update.")

        updated_variant = self.update_variant_price(
            variant_id=resolved_variant["id"],
            price=price,
        )
        return {
            "variant_id": updated_variant.get("id"),
            "product_id": updated_variant.get("product_id"),
            "inventory_item_id": updated_variant.get("inventory_item_id"),
            "sku": updated_variant.get("sku"),
            "price": updated_variant.get("price"),
        }

    def set_inventory_available(
        self,
        *,
        inventory_item_id: str | int,
        available: int,
        location_id: str | int | None = None,
    ) -> dict[str, Any]:
        resolved_location_id = location_id or self.default_location_id
        if not resolved_location_id:
            raise ValueError(
                "Missing location_id. Provide it in the request or set DEFAULT_LOCATION_ID."
            )

        body = {
            "location_id": int(resolved_location_id),
            "inventory_item_id": int(inventory_item_id),
            "available": int(available),
        }
        response = self._request("POST", "/inventory_levels/set.json", json=body)
        payload = self._parse_json(response)
        return payload.get("inventory_level", payload)

    def set_inventory_quantity(
        self,
        *,
        inventory_item_id: str | int,
        location_id: str | int | None,
        name: str,
        quantity: int,
        compare_quantity: int | None = None,
    ) -> dict[str, Any]:
        resolved_location_id = location_id or self.default_location_id
        if not resolved_location_id:
            raise ValueError(
                "Missing location_id. Provide it in the request or set DEFAULT_LOCATION_ID."
            )

        mutation = """
        mutation InventorySetQuantity($input: InventorySetQuantitiesInput!, $idempotencyKey: String!) {
          inventorySetQuantities(input: $input) @idempotent(key: $idempotencyKey) {
            inventoryAdjustmentGroup {
              reason
              changes {
                name
                delta
                quantityAfterChange
              }
            }
            userErrors {
              code
              field
              message
            }
          }
        }
        """
        variables = {
            "input": {
                "name": name,
                "reason": "correction",
                    "referenceDocumentUri": "m2m://shopify-import-export-tool/inventory-sync",
                "quantities": [
                    {
                        "inventoryItemId": f"gid://shopify/InventoryItem/{int(inventory_item_id)}",
                        "locationId": f"gid://shopify/Location/{int(resolved_location_id)}",
                        "quantity": int(quantity),
                        "compareQuantity": int(compare_quantity) if compare_quantity is not None else None,
                    }
                ],
            },
            "idempotencyKey": str(uuid.uuid4()),
        }
        data = self._graphql(mutation, variables=variables)
        result = data.get("inventorySetQuantities", {})
        user_errors = result.get("userErrors") or []
        if user_errors:
            raise ShopifyAPIError(
                f"Shopify rejected inventory update for `{name}`.",
                status_code=422,
                details=user_errors,
            )
        return result

    def update_stock(
        self,
        *,
        available: int | None = None,
        on_hand: int | None = None,
        unavailable: int | None = None,
        committed: int | None = None,
        sku: str | None = None,
        inventory_item_id: str | int | None = None,
        variant_id: str | int | None = None,
        location_id: str | int | None = None,
    ) -> dict[str, Any]:
        resolved_inventory_item_id = inventory_item_id
        resolved_variant: dict[str, Any] | None = None

        if resolved_inventory_item_id is None:
            if variant_id:
                resolved_variant = self.get_variant(variant_id)
                resolved_inventory_item_id = resolved_variant.get("inventory_item_id")
            elif sku:
                found = self.find_variant_by_sku(sku)
                resolved_variant = found["variant"]
                resolved_inventory_item_id = resolved_variant.get("inventory_item_id")

        if resolved_inventory_item_id is None:
            raise ShopifyAPIError(
                "Could not resolve inventory_item_id for stock update.",
                status_code=404,
                details={
                    "sku": sku,
                    "variant_id": variant_id,
                    "inventory_item_id": inventory_item_id,
                },
            )

        resolved_location_id = location_id or self.default_location_id
        current_quantities = self.get_inventory_snapshot(
            inventory_item_id=resolved_inventory_item_id,
            location_id=resolved_location_id,
        )
        targets = derive_inventory_targets(
            current_quantities=current_quantities,
            requested={
                "available": available,
                "on_hand": on_hand,
                "unavailable": unavailable,
                "committed": committed,
            },
        )

        current_available = int(current_quantities.get("available", 0) or 0)
        current_on_hand = int(current_quantities.get("on_hand", 0) or 0)
        available_changed = targets["available"] != current_available
        on_hand_changed = targets["on_hand"] != current_on_hand

        # Shopify requires on_hand >= available at every step, not only in the final state.
        # Increase on_hand first to create headroom, then update available, then decrease on_hand if needed.
        if on_hand_changed and targets["on_hand"] > current_on_hand:
            self.set_inventory_quantity(
                inventory_item_id=resolved_inventory_item_id,
                location_id=resolved_location_id,
                name="on_hand",
                quantity=targets["on_hand"],
                compare_quantity=current_on_hand,
            )
            current_quantities = self.get_inventory_snapshot(
                inventory_item_id=resolved_inventory_item_id,
                location_id=resolved_location_id,
            )
            current_on_hand = int(current_quantities.get("on_hand", 0) or 0)
            current_available = int(current_quantities.get("available", 0) or 0)

        if available_changed:
            self.set_inventory_quantity(
                inventory_item_id=resolved_inventory_item_id,
                location_id=resolved_location_id,
                name="available",
                quantity=targets["available"],
                compare_quantity=current_available,
            )
            current_quantities = self.get_inventory_snapshot(
                inventory_item_id=resolved_inventory_item_id,
                location_id=resolved_location_id,
            )
            current_on_hand = int(current_quantities.get("on_hand", 0) or 0)
            current_available = int(current_quantities.get("available", 0) or 0)

        if on_hand_changed and targets["on_hand"] < current_on_hand:
            self.set_inventory_quantity(
                inventory_item_id=resolved_inventory_item_id,
                location_id=resolved_location_id,
                name="on_hand",
                quantity=targets["on_hand"],
                compare_quantity=current_on_hand,
            )

        quantities = self.get_inventory_snapshot(
            inventory_item_id=resolved_inventory_item_id,
            location_id=resolved_location_id,
        )

        return {
            "inventory_item_id": int(resolved_inventory_item_id),
            "location_id": int(resolved_location_id) if resolved_location_id is not None else None,
            "available": quantities.get("available"),
            "on_hand": quantities.get("on_hand"),
            "unavailable": quantities.get("unavailable"),
            "sku": resolved_variant.get("sku") if resolved_variant else sku,
            "variant_id": resolved_variant.get("id") if resolved_variant else variant_id,
            "quantities": quantities,
        }

    def get_inventory_snapshot(
        self,
        *,
        inventory_item_id: str | int,
        location_id: str | int | None = None,
    ) -> dict[str, Any]:
        query = """
        query InventorySnapshot($id: ID!) {
          inventoryItem(id: $id) {
            id
            inventoryLevels(first: 25) {
              edges {
                node {
                  location {
                    id
                  }
                  quantities(names: ["available", "committed", "incoming", "on_hand", "reserved", "damaged", "quality_control", "safety_stock"]) {
                    name
                    quantity
                  }
                }
              }
            }
          }
        }
        """
        inventory_gid = f"gid://shopify/InventoryItem/{int(inventory_item_id)}"
        data = self._graphql(query, variables={"id": inventory_gid})
        item = data.get("inventoryItem")
        if not item:
            raise ShopifyAPIError(
                "Inventory snapshot not found for inventory item.",
                status_code=404,
                details={"inventory_item_id": inventory_item_id},
            )

        desired_location_gid = (
            f"gid://shopify/Location/{int(location_id)}" if location_id is not None else None
        )

        edges = item.get("inventoryLevels", {}).get("edges", [])
        for edge in edges:
            node = edge.get("node", {})
            location = node.get("location", {})
            if desired_location_gid and location.get("id") != desired_location_gid:
                continue

            quantities = {name: 0 for name in QUANTITY_NAMES}
            for quantity in node.get("quantities", []):
                quantities[quantity.get("name")] = quantity.get("quantity")

            on_hand = quantities.get("on_hand", 0) or 0
            available = quantities.get("available", 0) or 0
            quantities["unavailable"] = max(on_hand - available, 0)

            return {
                "location_id": location.get("id"),
                **quantities,
            }

        raise ShopifyAPIError(
            "No inventory level found for the requested location.",
            status_code=404,
            details={
                "inventory_item_id": inventory_item_id,
                "location_id": location_id,
            },
        )
