"""Джерело часу: окрема абстракція, щоб логіку можна було тестувати без реального очікування."""
import time
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def time(self) -> float:
        """Unix-час (переживає перезапуск процесу)."""

    def monotonic(self) -> float:
        """Для інтервалів усередині процесу."""

    def sleep(self, seconds: float) -> None: ...

    def now(self) -> datetime:
        """Місцевий час — для текстів повідомлень."""


class SystemClock:
    def __init__(self, tz: ZoneInfo) -> None:
        self._tz = tz

    def time(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def now(self) -> datetime:
        return datetime.now(self._tz)
