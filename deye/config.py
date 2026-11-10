"""Налаштування: типові значення + перевизначення змінними оточення (див. .env.example)."""
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from deye.model import Battery

PROJECT_DIR = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    """Неправильні або відсутні налаштування — текст пояснює, що виправити в .env."""


@dataclass(frozen=True)
class InverterConfig:
    host: str = ""
    serial: int = 0  # серійний номер Wi-Fi-логера (не інвертора!) — на наліпці LSW-3
    port: int = 8899
    slave_id: int = 1
    socket_timeout: int = 5  # с; інвертор відповідає за <1 с, довше — значить, зв'язку немає
    reconnect_delay: float = 1.0  # с; дати логеру звільнити слот перед новим з'єднанням

    def require(self) -> None:
        """Raises ConfigError, якщо не задано, куди підключатися."""
        missing = [name for name, value in (("INVERTER_HOST", self.host), ("INVERTER_SERIAL", self.serial))
                   if not value]
        if missing:
            raise ConfigError(f"не задано {', '.join(missing)} — впиши в .env (див. .env.example)")


@dataclass(frozen=True)
class TelegramConfig:
    token: str = ""
    admin: str = ""  # chat_id власника: службові повідомлення йдуть лише йому

    @property
    def enabled(self) -> bool:
        return bool(self.token)


@dataclass(frozen=True)
class Settings:
    inverter: InverterConfig = field(default_factory=InverterConfig)
    battery: Battery = field(default_factory=Battery)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    data_dir: Path = PROJECT_DIR / "data"
    tz: ZoneInfo = field(default_factory=lambda: ZoneInfo("Europe/Kyiv"))
    tariff: float = 4.32  # грн/кВт·год
    link_fails_to_report: int = 4  # стільки невдалих опитувань поспіль — і лише тоді повідомляти власника

    @property
    def users_file(self) -> Path:
        return self.data_dir / "users.json"

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "Settings":
        """Raises ConfigError, якщо значення змінної не розібрати."""
        get = _Env(env)
        inverter, battery, defaults = InverterConfig(), Battery(), cls()
        return cls(
            inverter=InverterConfig(
                host=get("INVERTER_HOST", str, inverter.host),
                serial=get("INVERTER_SERIAL", int, inverter.serial),
                port=get("INVERTER_PORT", int, inverter.port),
            ),
            battery=Battery(
                capacity_kwh=get("BATTERY_KWH", float, battery.capacity_kwh),
                min_soc=get("BATTERY_MIN_SOC", int, battery.min_soc),
                low_soc=get("BATTERY_LOW_SOC", int, battery.low_soc),
                low_soc_reset=get("BATTERY_LOW_SOC_RESET", int, battery.low_soc_reset),
            ),
            telegram=TelegramConfig(token=get("TELEGRAM_TOKEN", str, ""), admin=get("TELEGRAM_ADMIN", str, "")),
            data_dir=get("DATA_DIR", Path, defaults.data_dir),
            tz=get("TZ", ZoneInfo, defaults.tz),
            tariff=get("TARIFF", float, defaults.tariff),
        )


class _Env:
    """Читає змінну оточення й перетворює її; порожнє значення = типове."""

    def __init__(self, env: Mapping[str, str]) -> None:
        self._env = env

    def __call__[T](self, name: str, parse: Callable[[str], T], default: T) -> T:
        raw = self._env.get(name, "").strip()
        if not raw:
            return default
        try:
            return parse(raw)
        except (ValueError, ZoneInfoNotFoundError) as e:
            raise ConfigError(f"{name}={raw!r}: неправильне значення") from e

