import csv
import io
from typing import Any
from urllib.parse import urlparse


EXPORT_FIELDS = [
    "sku",
    "manufacturer",
    "product_name",
    "category",
    "price",
    "product_url",
    "image_url",
]


def normalize_shop_domain(shop_domain: str) -> str:
    value = shop_domain.strip()
    if value.startswith("http://") or value.startswith("https://"):
        value = urlparse(value).netloc
    return value.rstrip("/")


def first_image_url(product: dict[str, Any]) -> str:
    image = product.get("image") or {}
    if image.get("src"):
        return image["src"]

    images = product.get("images") or []
    if images and images[0].get("src"):
        return images[0]["src"]

    return ""


def product_url(shop_domain: str, handle: str) -> str:
    normalized = normalize_shop_domain(shop_domain)
    return f"https://{normalized}/products/{handle}"


def products_to_export_rows(
    products: list[dict[str, Any]],
    shop_domain: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for product in products:
        handle = product.get("handle") or ""
        image_url = first_image_url(product)
        manufacturer = product.get("vendor") or ""
        category = product.get("product_type") or ""
        name = product.get("title") or ""
        url = product_url(shop_domain, handle) if handle else ""

        for variant in product.get("variants") or []:
            sku = (variant.get("sku") or "").strip()
            if not sku:
                continue

            rows.append(
                {
                    "sku": sku,
                    "manufacturer": str(manufacturer),
                    "product_name": str(name),
                    "category": str(category),
                    "price": str(variant.get("price") or ""),
                    "product_url": url,
                    "image_url": image_url,
                }
            )

    return rows


def rows_to_csv(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
