"""Кому і як доставляти події: журнал + Telegram (якщо налаштований)."""
import logging
import re
from collections.abc import Callable

from deye.clock import Clock
from deye.storage import UserStore
from deye.telegram import TelegramBot

log = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")


def ring_bell() -> None:
    print("\a", end="", flush=True)  # BEL — звуковий сигнал у терміналі


class Notifier:
    def __init__(self, bot: TelegramBot | None, users: UserStore, admin: str, clock: Clock,
                 bell: Callable[[], None] = ring_bell) -> None:
        self._bot = bot
        self._users = users
        self._admin = admin
        self._clock = clock
        self._bell = bell

    def everyone(self, html: str) -> None:
        """Подія для всіх користувачів, зі звуком; час унизу — на випадок запізнілої доставки."""
        log.info(_TAG.sub("", html).replace("\n", "  ·  "))
        if self._bot:
            stamped = f"{html}\n<i>{self._clock.now():%H:%M}</i>"
            for chat_id, _ in self._users:
                self._bot.send(chat_id, stamped, html=True)
        self._bell()

    def admin(self, text: str) -> None:
        """Службове (запуск, зв'язок з інвертором, користувачі) — лише власнику, тихо."""
        log.info(text)
        if self._bot and self._admin:
            self._bot.send(self._admin, f"{self._clock.now():%H:%M}  {text}", silent=True)
