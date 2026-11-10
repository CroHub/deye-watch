"""Бот: надсилання з чергою на час відсутності інтернету і прийом вхідних."""
import json
import logging
import urllib.error
from collections import deque
from collections.abc import Sequence
from contextlib import suppress
from typing import Any

from deye.telegram.api import NETWORK_ERRORS, BotApi
from deye.telegram.message import Message, parse_update

log = logging.getLogger(__name__)

OUTBOX_SIZE = 200
Button = tuple[str, str]  # (підпис, callback data)
MenuItem = tuple[str, str]  # (команда без «/», опис)


class TelegramBot:
    def __init__(self, api: BotApi) -> None:
        self._api = api
        self._outbox: deque[dict[str, str | bool]] = deque(maxlen=OUTBOX_SIZE)
        self._online = True
        self._offset = 0

    @property
    def pending(self) -> int:
        """Скільки повідомлень чекають на інтернет."""
        return len(self._outbox)

    def me(self) -> dict[str, Any]:
        result: dict[str, Any] = self._api.call("getMe")["result"]
        return result

    def send(self, chat_id: str, text: str, *, silent: bool = False, html: bool = False,
             buttons: Sequence[Button] = ()) -> None:
        """buttons — inline-кнопки, по одній у рядку."""
        msg: dict[str, str | bool] = {"chat_id": chat_id, "disable_notification": silent, "text": text}
        if html:
            msg["parse_mode"] = "HTML"
        if buttons:
            keyboard = [[{"text": label, "callback_data": data}] for label, data in buttons]
            msg["reply_markup"] = json.dumps({"inline_keyboard": keyboard})
        self._outbox.append(msg)
        self.flush()

    def flush(self) -> None:
        """Досилає чергу по порядку; зупиняється на першому мережевому збої."""
        while self._outbox:
            msg = self._outbox[0]
            try:
                self._api.call("sendMessage", msg)
            except urllib.error.HTTPError as e:  # 4xx (токен, користувач заблокував бота): повтор не допоможе
                log.warning("! Telegram відхилив повідомлення для %s: %s %s",
                            msg["chat_id"], e.code, e.read().decode(errors="replace"))
            except NETWORK_ERRORS as e:
                if self._online:
                    log.warning("! Telegram недоступний (%s), повідомлень у черзі: %d", e, len(self._outbox))
                    self._online = False
                return
            self._outbox.popleft()
            self._online = True

    def receive(self, wait: int) -> list[Message]:
        """Чекає до wait секунд на нові текстові повідомлення та натискання кнопок (long polling).

        Raises: NETWORK_ERRORS, ValueError (биті дані).
        """
        updates = self._api.call("getUpdates", {"offset": self._offset, "timeout": wait}, timeout=wait + 10)["result"]
        messages = []
        for update in updates:
            self._offset = update["update_id"] + 1
            if msg := parse_update(update):
                messages.append(msg)
        return messages

    def set_menu(self, items: Sequence[MenuItem], chat_id: str = "") -> None:
        """Меню команд: для всіх або (chat_id) для одного чату."""
        params: dict[str, str] = {"commands": json.dumps([{"command": c, "description": d} for c, d in items])}
        if chat_id:
            params["scope"] = json.dumps({"type": "chat", "chat_id": int(chat_id)})
        with suppress(*NETWORK_ERRORS):
            self._api.call("setMyCommands", params)

    def answer_button(self, msg: Message, result: str) -> None:
        """Прибирає «годинник» з кнопки і замінює повідомлення з кнопками на результат."""
        with suppress(*NETWORK_ERRORS):
            self._api.call("answerCallbackQuery", {"callback_query_id": msg.callback_id})
            self._api.call("editMessageText", {"chat_id": msg.chat_id, "message_id": msg.message_id, "text": result})
