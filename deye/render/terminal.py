"""Звіт для терміналу (команди info і live)."""
from deye.clock import Clock
from deye.model import Battery, Reading, diagnose
from deye.render.format import charge_eta, duration, text_bar


class TerminalReport:
    def __init__(self, battery: Battery, tariff: float, clock: Clock, color: bool = False) -> None:
        self._battery = battery
        self._tariff = tariff
        self._clock = clock
        self._color = color

    def render(self, r: Reading, extra: str = "") -> str:
        lines = [
            f"{self._clock.now():%H:%M:%S}  Deye 5K ─ {r.state_name}{extra}",
            *self._status(r),
            "",
            *self._flow(r),
            "",
            *self._totals(r),
        ]
        if issues := diagnose(r, self._battery):
            lines.append("⚠  " + "  ·  ".join(i.text for i in issues))
        return "\n".join(lines)

    def _status(self, r: Reading) -> list[str]:
        grid = f"МЕРЕЖА   ● є      {r.grid_v:.0f} V  {r.grid_hz:.2f} Hz" if r.grid_on else "МЕРЕЖА   ✕ немає"
        battery = (f"АКБ      {text_bar(r.soc, color=self._color)}  {r.soc} %   {r.batt_v:.2f} V   "
                   f"{r.batt_t:.0f} °C   {self._battery.reserve_kwh(r):.1f} кВт·год")
        return [grid, battery]

    def _flow(self, r: Reading) -> list[str]:
        load = f"Квартира  {r.load_w:4d} W  ({r.load_a:.2f} A)"
        if not r.grid_on:
            autonomy = duration(self._battery.autonomy_h(r))
            return [
                f"АКБ ─{r.batt_w:4d} W──► {load}     автономія ≈ {autonomy} (до {self._battery.min_soc} %)",
                f"Інвертор бере на себе {r.batt_w - r.load_w} W",
            ]
        if r.charging:
            own_w = r.grid_w - r.load_w + r.batt_w
            efficiency = -r.batt_w / (r.grid_w - r.load_w) * 100 if r.grid_w > r.load_w else 0.0
            return [
                f"Мережа ─{r.grid_w:4d} W─┬─► {load}",
                f"{'':15}└─► АКБ       {-r.batt_w:4d} W  заряд   {charge_eta(r, self._battery)}",
                f"Інвертор бере на себе {own_w} W  ·  ККД заряду {efficiency:.0f} %",
            ]
        if r.discharging:  # мережа є, але АКБ віддає (пік/режим)
            return [f"Мережа ─{r.grid_w:4d} W─┬─► {load}", f"АКБ    ─{r.batt_w:4d} W─┘   розряд"]
        return [f"Мережа ─{r.grid_w:4d} W──► {load}     АКБ повна, простій"]

    def _totals(self, r: Reading) -> list[str]:
        return [
            f"Сьогодні   квартира {r.day_load:.1f} кВт·год  ·  з мережі {r.day_buy:.1f} "
            f"(≈ {r.day_buy * self._tariff:.0f} грн)  ·  АКБ +{r.day_chg:.1f} / −{r.day_dis:.1f}",
            f"Залізо     радіатор {r.t_heat:.0f} °C  ·  трансформатор {r.t_trans:.0f} °C",
        ]
