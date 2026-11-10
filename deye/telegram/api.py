"""Тонкий HTTP-клієнт Bot API: лише транспорт, без логіки."""
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol

# мережеві збої, коли повтор має сенс (HTTPError — підклас URLError, його обробляють окремо й раніше)
NETWORK_ERRORS: tuple[type[Exception], ...] = (urllib.error.URLError, OSError)

Params = Mapping[str, str | bool | int]


class BotApi(Protocol):
    def call(self, method: str, params: Params | None = None, timeout: int = 10) -> dict[str, Any]:
        """Raises: urllib.error.HTTPError — відмова API; NETWORK_ERRORS — немає зв'язку."""


class TelegramApi:
    def __init__(self, token: str) -> None:
        self._base = f"https://api.telegram.org/bot{token}/"

    def call(self, method: str, params: Params | None = None, timeout: int = 10) -> dict[str, Any]:
        data = urllib.parse.urlencode(params or {}).encode()
        with urllib.request.urlopen(self._base + method, data=data, timeout=timeout) as response:
            result: dict[str, Any] = json.load(response)
            return result
