"""Правила сповіщень. Кожне стежить за одним аспектом і саме вирішує, коли повідомити."""
import logging
from typing import Protocol

from deye.clock import Clock
from deye.inverter import describe_error
from deye.model import Battery, Reading
from deye.render import TelegramTexts
from deye.render.format import duration, elapsed, soc_icon
from deye.storage import GridState, GridStateStore
from deye.watch.notifier import Notifier

log = logging.getLogger(__name__)


class Alarm(Protocol):
    def check(self, r: Reading) -> None: ...


class LowBatteryAlarm:
    """«АКБ сідає» — усім, один раз за розряд (гістерезис: повторно лише після підзарядки)."""

    def __init__(self, battery: Battery, notifier: Notifier, texts: TelegramTexts) -> None:
        self._battery = battery
        self._notifier = notifier
        self._texts = texts
        self._warned = False

    def check(self, r: Reading) -> None:
        if self._battery.is_running_low(r) and not self._warned:
            self._notifier.everyone(self._texts.battery_low(r))
            self._warned = True
        elif r.soc >= self._battery.low_soc_reset:
            self._warned = False


class GridAlarm:
    """Зникнення/поява мережі — усім. Стан переживає перезапуск завдяки GridStateStore."""

    def __init__(self, store: GridStateStore, notifier: Notifier, texts: TelegramTexts, clock: Clock) -> None:
        self._store = store
        self._notifier = notifier
        self._texts = texts
        self._clock = clock
        self._state: GridState | None = None

    def check(self, r: Reading) -> None:
        if self._state is None:
            self._state = self._resume(r)
        elif r.grid_on != self._state.grid_on:
            self._state = self._switch(r, self._state)
        else:
            return
        self._store.save(self._state)

    def since(self, grid_on: bool) -> float | None:
        """Unix-час, відколи мережа в стані grid_on (None — ще не знаємо або стан щойно змінився)."""
        if self._state is None or self._state.grid_on != grid_on:
            return None
        return self._state.since

    def _resume(self, r: Reading) -> GridState:
        """Перше опитування: якщо стан не змінився, поки нас не було, — продовжуємо відлік."""
        saved = self._store.load()
        state = saved if saved and saved.grid_on == r.grid_on else GridState(r.grid_on, self._clock.time())
        how_long = f" вже {self._elapsed(state)}" if state is saved else ""
        self._notifier.admin(f"👀 стежу за мережею: {'Є' if r.grid_on else 'НЕМАЄ'}{how_long}"
                             f"  ·  АКБ {soc_icon(r.soc)} {r.soc} %")
        return state

    def _switch(self, r: Reading, previous: GridState) -> GridState:
        was = self._elapsed(previous)
        self._notifier.everyone(self._texts.grid_restored(r, was) if r.grid_on else self._texts.grid_lost(r, was))
        return GridState(r.grid_on, self._clock.time())

    def _elapsed(self, state: GridState) -> str:
        return elapsed(self._clock.time() - state.since)


class LinkHealth:
    """Втрата зв'язку з інвертором. Wi-Fi-логер час від часу «блимає» — такі збої лише в журнал;
    власнику пишемо, коли невдач поспіль набралось threshold, і потім — про відновлення."""

    def __init__(self, notifier: Notifier, clock: Clock, threshold: int) -> None:
        self._notifier = notifier
        self._clock = clock
        self._threshold = threshold
        self._fails = 0
        self._lost_at = 0.0

    def failed(self, error: BaseException) -> None:
        self._fails += 1
        reason = describe_error(error)
        if self._fails == 1:
            self._lost_at = self._clock.monotonic()
            log.info("! немає відповіді від інвертора: %s", reason)
        if self._fails == self._threshold:
            self._notifier.admin(f"⚠️ немає зв'язку з інвертором вже {self._outage()}: {reason}")

    def recovered(self) -> None:
        if self._fails >= self._threshold:
            self._notifier.admin(f"🔌 зв'язок з інвертором відновлено, не було {self._outage()}")
        elif self._fails:
            log.info("зв'язок з інвертором відновлено")
        self._fails = 0

    def _outage(self) -> str:
        return duration((self._clock.monotonic() - self._lost_at) / 3600)
