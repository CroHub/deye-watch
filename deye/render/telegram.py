"""Тексти для Telegram (HTML): вузькі, під телефон, з кольоровою шкалою заряду."""
from deye.clock import Clock
from deye.model import Battery, Reading, diagnose
from deye.render.format import charge_eta, duration, emoji_bar


class TelegramTexts:
    def __init__(self, battery: Battery, tariff: float, clock: Clock) -> None:
        self._battery = battery
        self._tariff = tariff
        self._clock = clock

    # --- звіт /info ---

    def report(self, r: Reading, admin: bool = False) -> str:
        """Технічні попередження (стан інвертора, температура, напруга) — лише власнику."""
        issues = [i for i in diagnose(r, self._battery) if admin or not i.technical]
        lines = [f"⚠️ <b>{i.text}</b>" for i in issues]
        if lines:
            lines.append("")
        lines += [*self._status(r), "", *self._flow(r), "", *self._totals(r)]
        return "\n".join(lines)

    def _status(self, r: Reading) -> list[str]:
        if r.grid_on:
            grid = f"⚡ <b>Мережа є</b>  ·  {r.grid_v:.0f} V  ·  {r.grid_hz:.2f} Hz"
        else:
            grid = "✕ <b>Мережі немає</b>"
        details = (f"<i>{r.batt_v:.1f} V  ·  {r.batt_t:.0f} °C  ·  "
                   f"запас {self._battery.reserve_kwh(r):.1f} кВт·год</i>")
        return [grid, self.battery(r), details]

    def _flow(self, r: Reading) -> list[str]:
        lines = [f"🏠 Квартира  <b>{r.load_w} W</b>  ({r.load_a:.1f} A)"]
        if r.grid_on:
            lines.append(f"🔌 З мережі  {r.grid_w} W")
        if r.charging:
            lines.append(f"⬆️ Заряд АКБ  {-r.batt_w} W  ·  {charge_eta(r, self._battery)}")
        elif r.discharging:
            line = f"⬇️ Від АКБ  {r.batt_w} W"
            if not r.grid_on:
                hours = duration(self._battery.autonomy_h(r))
                line += f"  ·  вистачить ≈ <b>{hours}</b> (до {self._battery.min_soc} %)"
            lines.append(line)
        else:
            lines.append("💤 АКБ не працює")
        return lines

    def _totals(self, r: Reading) -> list[str]:
        return [
            "📊 <b>Сьогодні</b>",
            f"Квартира спожила  {r.day_load:.1f} кВт·год",
            f"З мережі  {r.day_buy:.1f} кВт·год  ≈ {r.day_buy * self._tariff:.0f} грн",
            f"АКБ  +{r.day_chg:.1f} / −{r.day_dis:.1f} кВт·год",
            "",
            f"🌡 Радіатор {r.t_heat:.0f} °C  ·  трансформатор {r.t_trans:.0f} °C",
            f"<i>Deye 5K · {r.state_name} · {self._clock.now():%H:%M:%S}</i>",
        ]

    # --- події для всіх користувачів ---

    def battery(self, r: Reading) -> str:
        icon = "🪫" if self._battery.is_low(r) else "🔋"
        return f"{icon} <b>{r.soc} %</b>   {emoji_bar(r.soc)}"

    def grid_restored(self, r: Reading, was_off: str) -> str:
        return f"🟢 <b>Світло з'явилось</b>  ·  {r.grid_v:.0f} V\nне було {was_off}\n{self.battery(r)}"

    def grid_lost(self, r: Reading, was_on: str) -> str:
        return f"🔴 <b>Світло зникло</b>\nбуло {was_on}\n{self.battery(r)}\n{self._autonomy(r)}"

    def battery_low(self, r: Reading) -> str:
        return f"🪫 <b>АКБ сідає: {r.soc} %</b>   {emoji_bar(r.soc)}\n{self._autonomy(r)}"

    def _autonomy(self, r: Reading) -> str:
        hours = duration(self._battery.autonomy_estimate_h(r))
        return f"🏠 {r.load_w} W  ·  вистачить ≈ <b>{hours}</b> (до {self._battery.min_soc} %)"
