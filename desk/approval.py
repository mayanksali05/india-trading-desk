"""How EXECUTOR asks you before placing anything.

observe  : week 1. Never approves; everything is logged so you can read the desk's reasoning.
console  : y/n prompt in the terminal.
telegram : Approve / Reject buttons on your phone. No answer before the timeout = rejected."""
from __future__ import annotations

import logging
import secrets
import time

import requests

from desk.models import NewsNote, Order, Ruling

log = logging.getLogger("desk")


def describe(order: Order, ruling: Ruling, note: NewsNote) -> str:
    reasons = "\n".join(f"  - {r}" for r in ruling.reasons) or "  - (none given)"
    return (
        f"Approval needed: BUY {order.qty} {order.symbol} near ₹{order.entry}\n"
        f"Stop ₹{order.stop} | Target ₹{order.target}\n"
        f"News: {note.reason}\n"
        f"Skeptic ruled {ruling.verdict.value}, despite:\n{reasons}"
    )


class ObserveApprover:
    def ask(self, order: Order, ruling: Ruling, note: NewsNote) -> bool:
        log.info("OBSERVE mode, not placed:\n%s", describe(order, ruling, note))
        return False

    def notify(self, text: str) -> None:
        log.info(text)


class ConsoleApprover:
    def ask(self, order: Order, ruling: Ruling, note: NewsNote) -> bool:
        print("\n" + describe(order, ruling, note))
        return input("Approve? [y/N] ").strip().lower() == "y"

    def notify(self, text: str) -> None:
        print(text)


class TelegramApprover:
    def __init__(self, token: str, chat_id: str, timeout_minutes: float):
        if not token or not chat_id:
            raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set for approval: telegram")
        self.api = f"https://api.telegram.org/bot{token}"
        self.chat_id = str(chat_id)
        self.timeout_s = timeout_minutes * 60
        self.offset = None

    def _call(self, method: str, **params):
        r = requests.post(f"{self.api}/{method}", json=params, timeout=40)
        r.raise_for_status()
        return r.json()["result"]

    def notify(self, text: str) -> None:
        try:
            self._call("sendMessage", chat_id=self.chat_id, text=text)
        except Exception as e:
            log.error("Telegram notify failed: %s", e)

    def ask(self, order: Order, ruling: Ruling, note: NewsNote) -> bool:
        nonce = secrets.token_hex(4)
        msg = self._call(
            "sendMessage", chat_id=self.chat_id, text=describe(order, ruling, note),
            reply_markup={"inline_keyboard": [[
                {"text": "Approve", "callback_data": f"ok:{nonce}"},
                {"text": "Reject", "callback_data": f"no:{nonce}"},
            ]]},
        )
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            params = {"timeout": 25, "allowed_updates": ["callback_query"]}
            if self.offset is not None:
                params["offset"] = self.offset
            for update in self._call("getUpdates", **params):
                self.offset = update["update_id"] + 1
                cq = update.get("callback_query")
                if not cq or not cq.get("data", "").endswith(nonce):
                    continue
                if str(cq["from"]["id"]) != self.chat_id:
                    continue  # only you can approve
                approved = cq["data"].startswith("ok:")
                self._call("answerCallbackQuery", callback_query_id=cq["id"])
                self._call("editMessageReplyMarkup", chat_id=self.chat_id, message_id=msg["message_id"],
                           reply_markup={"inline_keyboard": []})
                return approved
        self.notify(f"Approval for {order.symbol} expired. Not placed.")
        return False
