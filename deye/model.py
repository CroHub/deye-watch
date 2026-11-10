"""Доменна модель: знімок стану інвертора, АКБ і діагностика."""
from dataclasses import dataclass

NORMAL_STATE = 2
STATE_NAMES = {0: "Standby", 1: "Self-check", NORMAL_STATE: "Normal", 3: "Alarm", 4: "Fault"}
HOT_C = 65  # вище — «інвертор гарячий»
LOW_GRID_V = 200  # нижче — «низька напруга мережі»


@dataclass(frozen=True)
class Reading:
    """Один знімок регістрів інвертора в людських одиницях."""

    state: int
    grid_on: bool
    grid_v: float
    grid_hz: float
    grid_w: int
    grid_a: float
    load_w: int
    load_v: float
    inv_w: int
    soc: int
    batt_v: float
    batt_a: float  # − заряд, + розряд
    batt_w: int  # − заряд, + розряд
    batt_t: float
    t_heat: float
    t_trans: float
    day_chg: float
    day_dis: float
    day_buy: float
    day_load: float

    @property
    def load_a(self) -> float:
        return self.load_w / self.load_v if self.load_v > 50 else 0.0

    @property
    def state_name(self) -> str:
        return STATE_NAMES.get(self.state, str(self.state))

    @property
    def charging(self) -> bool:
        return self.batt_w < 0

    @property
    def discharging(self) -> bool:
        return self.batt_w > 0


@dataclass(frozen=True)
class Battery:
    """Параметри АКБ і розрахунки запасу енергії."""

    capacity_kwh: float = 5.0
    min_soc: int = 20  # до якого SOC рахуємо автономію
    low_soc: int = 25  # нижче — попередження «АКБ сідає»
    low_soc_reset: int = 30  # повторне попередження — лише після підзарядки вище цього рівня

    def reserve_kwh(self, r: Reading) -> float:
        """Енергія в АКБ понад min_soc."""
        return self.capacity_kwh * max(r.soc - self.min_soc, 0) / 100

    def autonomy_h(self, r: Reading) -> float | None:
        """Скільки годин АКБ протримає поточний розряд до min_soc (None — не розряджається)."""
        return self._hours_at(r, r.batt_w)

    def autonomy_estimate_h(self, r: Reading) -> float | None:
        """Як autonomy_h, але в момент перемикання, коли АКБ ще не почала віддавати, рахує за навантаженням."""
        return self._hours_at(r, max(r.batt_w, r.load_w))

    def full_charge_h(self, r: Reading) -> float | None:
        """Скільки годин до 100 % при поточному заряді (None — не заряджається)."""
        if not r.charging:
            return None
        return self.capacity_kwh * (100 - r.soc) / 100 / (-r.batt_w / 1000)

    def is_low(self, r: Reading) -> bool:
        return r.soc < self.low_soc

    def is_running_low(self, r: Reading) -> bool:
        return r.discharging and self.is_low(r)

    def _hours_at(self, r: Reading, watts: int) -> float | None:
        return self.reserve_kwh(r) / (watts / 1000) if watts > 0 else None


@dataclass(frozen=True)
class Issue:
    """Попередження про стан системи. technical — лише для власника."""

    text: str
    technical: bool = True


BATTERY_LOW = "АКБ скоро сяде"


def diagnose(r: Reading, battery: Battery) -> list[Issue]:
    issues = []
    if r.state != NORMAL_STATE:
        issues.append(Issue(f"стан інвертора: {r.state_name}"))
    if max(r.t_heat, r.t_trans) > HOT_C:
        issues.append(Issue("інвертор гарячий"))
    if r.grid_on and r.grid_v < LOW_GRID_V:
        issues.append(Issue(f"низька напруга мережі {r.grid_v:.0f} V"))
    if battery.is_running_low(r):
        issues.append(Issue(BATTERY_LOW, technical=False))
    return issues
