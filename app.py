import os
import threading
import time
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

from export_utils import products_to_export_rows, rows_to_csv
from shopify_client import ConfigError, ShopifyAPIError, ShopifyClient


load_dotenv()


APP_NAME = "shopify-import-export-tool"
API_VERSION = "2026-01"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


def create_shopify_client() -> ShopifyClient:
    shop_domain = _env("SHOP_DOMAIN")
    access_token = _env("SHOPIFY_ACCESS_TOKEN")
    default_location_id = _env("DEFAULT_LOCATION_ID")

    if not shop_domain:
        raise ConfigError("Missing SHOP_DOMAIN in environment.")
    if not access_token:
        raise ConfigError("Missing SHOPIFY_ACCESS_TOKEN in environment.")

    return ShopifyClient(
        shop_domain=shop_domain,
        access_token=access_token,
        api_version=API_VERSION,
        default_location_id=default_location_id,
    )


app = Flask(__name__)


def _is_local_request() -> bool:
    return request.remote_addr in {"127.0.0.1", "::1", "localhost"}


def _shutdown_after_response() -> None:
    time.sleep(0.4)
    os._exit(0)


@app.get("/")
def dashboard() -> Response:
    return render_template(
        "dashboard.html",
        app_name=APP_NAME,
        api_version=API_VERSION,
        shop_domain=_env("SHOP_DOMAIN") or "not-configured",
        default_location_id=_env("DEFAULT_LOCATION_ID") or "not-configured",
    )


@app.post("/admin/shutdown")
def shutdown_app() -> Response:
    if not _is_local_request():
        return _json_error("Shutdown is allowed only from localhost.", 403)

    threading.Thread(target=_shutdown_after_response, daemon=True).start()
    return (
        jsonify(
            {
                "success": True,
                "message": "Application is shutting down.",
            }
        ),
        200,
    )


@app.get("/health")
def health() -> Response:
    issues: list[str] = []
    if not _env("SHOP_DOMAIN"):
        issues.append("SHOP_DOMAIN is not configured")
    if not _env("SHOPIFY_ACCESS_TOKEN"):
        issues.append("SHOPIFY_ACCESS_TOKEN is not configured")
    if not _env("DEFAULT_LOCATION_ID"):
        issues.append("DEFAULT_LOCATION_ID is not configured")

    payload = {
        "ok": len(issues) == 0,
        "service": APP_NAME,
        "api_version": API_VERSION,
        "shop_domain": _env("SHOP_DOMAIN"),
        "default_location_id": _env("DEFAULT_LOCATION_ID"),
        "issues": issues,
    }
    status_code = 200 if not issues else 503
    return jsonify(payload), status_code


def _get_json_body() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a valid JSON object.")
    return payload


def _parse_price(value) -> str:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Field `price` must be a valid decimal value.") from exc

    if price < 0:
        raise ValueError("Field `price` must be greater than or equal to 0.")

    return format(price.quantize(Decimal("0.01")), "f")


def _parse_available(value) -> int:
    try:
        available = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Field `available` must be a valid integer.") from exc

    return available


def _parse_optional_int(name: str, value):
    if value in (None, ""):
        return None

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field `{name}` must be a valid integer.") from exc

    return parsed


def _json_error(message: str, status_code: int, **extra) -> tuple[Response, int]:
    payload = {"success": False, "error": message}
    payload.update(extra)
    return jsonify(payload), status_code


@app.post("/incoming/update-price")
def update_price() -> Response:
    try:
        body = _get_json_body()
        client = create_shopify_client()

        sku = body.get("sku")
        variant_id = body.get("variant_id")
        price = _parse_price(body.get("price"))

        if not sku and not variant_id:
            raise ValueError("Provide either `sku` or `variant_id`.")

        result = client.update_price(price=price, sku=sku, variant_id=variant_id)
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Price updated successfully.",
                    "data": result,
                }
            ),
            200,
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except ConfigError as exc:
        return _json_error(str(exc), 500)
    except ShopifyAPIError as exc:
        return _json_error(str(exc), exc.status_code or 502, details=exc.details)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return _json_error("Unexpected server error.", 500, details=str(exc))


@app.post("/incoming/update-stock")
def update_stock() -> Response:
    try:
        body = _get_json_body()
        client = create_shopify_client()

        sku = body.get("sku")
        inventory_item_id = body.get("inventory_item_id")
        variant_id = body.get("variant_id")
        location_id = body.get("location_id")
        available = _parse_optional_int("available", body.get("available"))

        if not sku and not inventory_item_id and not variant_id:
            raise ValueError(
                "Provide one of `sku`, `inventory_item_id`, or `variant_id`."
            )

        if available is None:
            raise ValueError("Provide `available`.")

        result = client.update_stock(
            available=available,
            sku=sku,
            inventory_item_id=inventory_item_id,
            variant_id=variant_id,
            location_id=location_id,
        )
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Stock updated successfully.",
                    "data": result,
                }
            ),
            200,
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    except ConfigError as exc:
        return _json_error(str(exc), 500)
    except ShopifyAPIError as exc:
        return _json_error(str(exc), exc.status_code or 502, details=exc.details)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return _json_error("Unexpected server error.", 500, details=str(exc))


@app.get("/outgoing/products.json")
def outgoing_products_json() -> Response:
    try:
        client = create_shopify_client()
        products = client.get_products_for_export()
        rows = products_to_export_rows(products, client.shop_domain)
        return jsonify({"success": True, "count": len(rows), "products": rows}), 200
    except ConfigError as exc:
        return _json_error(str(exc), 500)
    except ShopifyAPIError as exc:
        return _json_error(str(exc), exc.status_code or 502, details=exc.details)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return _json_error("Unexpected server error.", 500, details=str(exc))


@app.get("/outgoing/products.csv")
def outgoing_products_csv() -> Response:
    try:
        client = create_shopify_client()
        products = client.get_products_for_export()
        rows = products_to_export_rows(products, client.shop_domain)
        csv_content = rows_to_csv(rows)

        return Response(
            csv_content,
            mimetype="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=shopify-products-export.csv"
            },
        )
    except ConfigError as exc:
        return _json_error(str(exc), 500)
    except ShopifyAPIError as exc:
        return _json_error(str(exc), exc.status_code or 502, details=exc.details)
    except Exception as exc:  # pragma: no cover - defensive fallback
        return _json_error("Unexpected server error.", 500, details=str(exc))


if __name__ == "__main__":
    port = int(_env("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
