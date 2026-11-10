"""Спільні форматери: тривалість, шкала заряду, час до повного заряду."""
from deye.model import Battery, Reading

SOC_BANDS = (25, 35, 60)  # межі рівнів заряду: критично < 25 ≤ низько < 35 ≤ середньо < 60 ≤ добре
_SOC_ANSI = ("\033[31m", "\033[33m", "\033[93m", "\033[32m")  # червоний, помаранчевий, жовтий, зелений
_SOC_EMOJI = ("🟥", "🟧", "🟨", "🟩")
_ANSI_RESET = "\033[0m"


def duration(hours: float | None) -> str:
    """2.25 → «2 год 15 хв»; невідомо або нереально довго → «—»."""
    if hours is None or hours <= 0 or hours > 99:
        return "—"
    h, m = divmod(round(hours * 60), 60)
    return f"{h} год {m:02d} хв" if h else f"{m} хв"


def soc_level(pct: int) -> int:
    """0 — критично, 1 — низько, 2 — середньо, 3 — добре."""
    return sum(pct >= band for band in SOC_BANDS)


def soc_icon(pct: int) -> str:
    return _SOC_EMOJI[soc_level(pct)]


def emoji_bar(pct: int, cells: int = 10) -> str:
    """Шкала для Telegram; будь-який ненульовий заряд — хоча б одна клітинка."""
    n = max(round(pct / 100 * cells), 1 if pct > 0 else 0)
    return soc_icon(pct) * n + "⬜" * (cells - n)


def text_bar(pct: int, width: int = 22, color: bool = False) -> str:
    """Шкала для терміналу, кольорова — лише якщо термінал це підтримує."""
    n = round(pct / 100 * width)
    text = "█" * n + "░" * (width - n)
    return f"{_SOC_ANSI[soc_level(pct)]}{text}{_ANSI_RESET}" if color else text


def charge_eta(r: Reading, battery: Battery) -> str:
    """Скільки ще заряджатись до 100 % (текстом)."""
    if r.soc >= 99:
        return "майже повна"
    hours = battery.full_charge_h(r)
    return "—" if hours is None else f"до 100 % ≈ {duration(hours)}"
