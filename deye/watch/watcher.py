"""Цикл стеження: опитати інвертор → перевірити правила → чекати (і відповідати в боті)."""
from collections.abc import Callable, Sequence
from typing import Protocol

from deye.clock import Clock
from deye.inverter import LINK_ERRORS
from deye.model import Reading
from deye.telegram import NETWORK_ERRORS, Message, TelegramBot
from deye.watch.alarms import Alarm, LinkHealth

_RECEIVE_ERRORS: tuple[type[Exception], ...] = (*NETWORK_ERRORS, ValueError)  # ValueError — биті дані


class Monitor:
    """Одне опитування: читання + передача знімка всім правилам."""

    def __init__(self, read: Callable[[], Reading], health: LinkHealth, alarms: Sequence[Alarm]) -> None:
        self._read = read
        self._health = health
        self._alarms = alarms

    def poll(self) -> None:
        try:
            r = self._read()
        except LINK_ERRORS as e:
            self._health.failed(e)
            return
        self._health.recovered()
        for alarm in self._alarms:
            alarm.check(r)


class Pause(Protocol):
    def wait(self, seconds: int) -> None: ...


class Sleep:
    """Пауза без бота."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def wait(self, seconds: int) -> None:
        self._clock.sleep(seconds)


class BotListener:
    """Пауза, під час якої слухаємо бота, щоб відповідати на команди одразу."""

    def __init__(self, bot: TelegramBot, handle: Callable[[Message], None], clock: Clock) -> None:
        self._bot = bot
        self._handle = handle
        self._clock = clock

    def wait(self, seconds: int) -> None:
        deadline = self._clock.monotonic() + seconds
        while (left := int(deadline - self._clock.monotonic())) > 0:
            self._bot.flush()  # дослати те, що не пішло, коли не було інтернету
            try:
                incoming = self._bot.receive(left)
            except _RECEIVE_ERRORS:
                self._clock.sleep(left)
                return
            for msg in incoming:
                self._handle(msg)


class Watcher:
    def __init__(self, monitor: Monitor, pause: Pause, interval: int) -> None:
        self._monitor = monitor
        self._pause = pause
        self._interval = interval

    def run(self) -> None:
        """Нескінченний цикл; зупиняється KeyboardInterrupt."""
        while True:
            self._monitor.poll()
            self._pause.wait(self._interval)
