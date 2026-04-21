from html import escape
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

from shopify_client import ConfigError, ShopifyAPIError


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramCommand:
    name: str
    args: list[str]


@dataclass(frozen=True)
class TelegramMessage:
    text: str
    parse_mode: str | None = None


@dataclass(frozen=True)
class TelegramResponse:
    text: str
    extra_messages: list[TelegramMessage] | None = None


TELEGRAM_MESSAGE_LIMIT = 3500


def parse_telegram_command(text: str | None) -> TelegramCommand | None:
    if not text:
        return None

    stripped = text.strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped.split()
    if not parts:
        return None

    command_name = parts[0].split("@", 1)[0].lower()
    return TelegramCommand(name=command_name, args=parts[1:])


def parse_allowed_chat_ids(raw_value: str | None) -> set[int]:
    if not raw_value:
        return set()

    allowed_ids: set[int] = set()
    for part in raw_value.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        allowed_ids.add(int(candidate))
    return allowed_ids


class TelegramBotService:
    def __init__(
        self,
        *,
        token: str,
        allowed_chat_ids: set[int],
        create_shopify_client: Callable[[], Any],
        parse_price: Callable[[Any], str],
        list_products: Callable[[], list[dict[str, str]]],
    ) -> None:
        self.token = token.strip()
        self.allowed_chat_ids = allowed_chat_ids
        self.create_shopify_client = create_shopify_client
        self.parse_price = parse_price
        self.list_products = list_products
        self.session = requests.Session()
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.offset: int | None = None
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> bool:
        if self.thread and self.thread.is_alive():
            return False

        self._prime_offset()
        self.thread = threading.Thread(
            target=self._poll_loop,
            name="telegram-bot-polling",
            daemon=True,
        )
        self.thread.start()
        LOGGER.info("Telegram bot polling started.")
        return True

    def _prime_offset(self) -> None:
        try:
            updates = self._get_updates(timeout=0)
        except Exception as exc:  # pragma: no cover - network safeguard
            LOGGER.warning("Telegram bot could not read pending updates: %s", exc)
            return

        if updates:
            self.offset = max(int(update["update_id"]) for update in updates) + 1

    def _poll_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                updates = self._get_updates(timeout=20)
                for update in updates:
                    self.offset = int(update["update_id"]) + 1
                    self._handle_update(update)
            except Exception as exc:  # pragma: no cover - network safeguard
                LOGGER.exception("Telegram bot polling failed: %s", exc)
                time.sleep(3)

    def _request(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/{method}",
            json=payload,
            timeout=(5, 30),
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error for `{method}`: {data}")
        return data

    def _get_updates(self, *, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message"],
        }
        if self.offset is not None:
            payload["offset"] = self.offset
        data = self._request("getUpdates", payload)
        return data.get("result", [])

    def _handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        text = message.get("text")
        chat_id = chat.get("id")
        if chat_id is None:
            return

        if int(chat_id) not in self.allowed_chat_ids:
            LOGGER.warning("Rejected Telegram message from unauthorized chat %s.", chat_id)
            self._send_message(
                int(chat_id),
                "Chat neautorizat pentru acest bot.",
            )
            return

        command = parse_telegram_command(text)
        if command is None:
            self._send_message(int(chat_id), self._help_text())
            return

        response = self._execute_command(command)
        self._send_message(int(chat_id), response.text)
        for message in response.extra_messages or []:
            self._send_message(
                int(chat_id),
                message.text,
                parse_mode=message.parse_mode,
            )

    def _execute_command(self, command: TelegramCommand) -> TelegramResponse:
        try:
            if command.name in {"/start", "/help"}:
                return TelegramResponse(text=self._help_text())
            if command.name == "/health":
                return TelegramResponse(text=self._health_text())
            if command.name == "/stock":
                return TelegramResponse(text=self._handle_stock(command.args))
            if command.name == "/price":
                return TelegramResponse(text=self._handle_price(command.args))
            if command.name == "/products":
                return self._handle_products()
            return TelegramResponse(
                text=(
                    "Comanda nu exista.\n\n"
                    f"{self._help_text()}"
                )
            )
        except ValueError as exc:
            return TelegramResponse(text=f"Eroare de input: {exc}")
        except ConfigError as exc:
            return TelegramResponse(text=f"Configurare invalida: {exc}")
        except ShopifyAPIError as exc:
            return TelegramResponse(text=f"Shopify error: {exc}")
        except Exception as exc:  # pragma: no cover - defensive fallback
            LOGGER.exception("Telegram command failed: %s", exc)
            return TelegramResponse(text=f"Eroare neasteptata: {exc}")

    def _handle_stock(self, args: list[str]) -> str:
        if len(args) != 2:
            raise ValueError("Foloseste: /stock SKU CANTITATE")

        sku = args[0].strip()
        if not sku:
            raise ValueError("SKU nu poate fi gol.")

        try:
            available = int(args[1])
        except ValueError as exc:
            raise ValueError("Cantitatea trebuie sa fie numar intreg.") from exc

        client = self.create_shopify_client()
        result = client.update_stock(sku=sku, available=available)
        return (
            "Stock actualizat.\n"
            f"SKU: {result.get('sku') or sku}\n"
            f"Available: {result.get('available')}\n"
            f"On hand: {result.get('on_hand')}"
        )

    def _handle_price(self, args: list[str]) -> str:
        if len(args) != 2:
            raise ValueError("Foloseste: /price SKU PRET")

        sku = args[0].strip()
        if not sku:
            raise ValueError("SKU nu poate fi gol.")

        price = self.parse_price(args[1])
        client = self.create_shopify_client()
        result = client.update_price(sku=sku, price=price)
        return (
            "Pret actualizat.\n"
            f"SKU: {result.get('sku') or sku}\n"
            f"Price: {result.get('price')}"
        )

    def _health_text(self) -> str:
        client = self.create_shopify_client()
        default_location_id = getattr(client, "default_location_id", None) or "missing"
        return (
            "Bot OK.\n"
            f"Store: {client.shop_domain}\n"
            f"Default location: {default_location_id}"
        )

    def _handle_products(self) -> TelegramResponse:
        rows = self.list_products()
        count = len(rows)
        if count == 0:
            return TelegramResponse(text="Nu am gasit produse exportabile.")

        lines = []
        for index, row in enumerate(rows, start=1):
            sku = escape(row.get("sku") or "-")
            name = escape(row.get("product_name") or "-")
            price = escape(row.get("price") or "-")
            product_url = row.get("product_url") or ""

            if product_url:
                linked_name = f'<a href="{escape(product_url, quote=True)}">{name}</a>'
            else:
                linked_name = name

            lines.append(f"{index}. {sku} | {linked_name} | {price}")

        message_batches = [
            TelegramMessage(text=message, parse_mode="HTML")
            for message in self._chunk_messages(lines)
        ]
        return TelegramResponse(
            text=f"Lista produselor. Total randuri exportate: {count}",
            extra_messages=message_batches,
        )

    @staticmethod
    def _chunk_messages(lines: list[str]) -> list[str]:
        messages: list[str] = []
        current_lines: list[str] = []
        current_length = 0

        for line in lines:
            extra_length = len(line) + (1 if current_lines else 0)
            if current_lines and current_length + extra_length > TELEGRAM_MESSAGE_LIMIT:
                messages.append("\n".join(current_lines))
                current_lines = [line]
                current_length = len(line)
                continue

            current_lines.append(line)
            current_length += extra_length

        if current_lines:
            messages.append("\n".join(current_lines))

        return messages

    @staticmethod
    def _help_text() -> str:
        return (
            "Comenzi disponibile:\n"
            "/stock SKU CANTITATE\n"
            "/price SKU PRET\n"
            "/products\n"
            "/health"
        )

    def _send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
    ) -> None:
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        self._request("sendMessage", payload)
