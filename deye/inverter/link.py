"""З'єднання з Wi-Fi-логером Solarman LSW-3."""
import logging
import queue
from collections.abc import Callable
from contextlib import suppress

from pysolarmanv5 import NoSocketAvailableError, PySolarmanV5, V5FrameError
from umodbus.exceptions import ModbusError

from deye.config import InverterConfig
from deye.inverter.registers import ModbusClient, read_reading
from deye.model import Reading

log = logging.getLogger(__name__)

# помилки зв'язку/протоколу (TimeoutError — підклас OSError; queue.Empty — тайм-аут відповіді в pysolarmanv5)
LINK_ERRORS: tuple[type[BaseException], ...] = (OSError, NoSocketAvailableError, V5FrameError, ModbusError, queue.Empty)

Connector = Callable[[], ModbusClient]


def describe_error(e: BaseException) -> str:
    """Текст помилки зв'язку, ніколи не порожній (у queue.Empty він порожній)."""
    return str(e) or ("тайм-аут відповіді" if isinstance(e, queue.Empty) else type(e).__name__)


def solarman_connector(cfg: InverterConfig) -> Connector:
    """Raises ConfigError, якщо не задано адресу чи серійний номер логера."""
    cfg.require()

    def connect() -> ModbusClient:
        client: ModbusClient = PySolarmanV5(cfg.host, cfg.serial, port=cfg.port, mb_slave_id=cfg.slave_id,
                                            socket_timeout=cfg.socket_timeout)
        return client
    return connect


class Link:
    """Постійне з'єднання з логером + одна повторна спроба, якщо впало вже відкрите з'єднання.

    Логер LSW-3 раз на кілька годин сам рве TCP. Якщо запит на «старому» з'єднанні не вдався —
    закриваємо, через reconnect_delay відкриваємо нове й повторюємо. Якщо не вдалося й на свіжому —
    це справжня втрата зв'язку: виняток іде нагору, наступна спроба — на наступному опитуванні
    (жодних циклів перепідключення). auto_reconnect бібліотеки свідомо не вмикаємо: його потік
    перепідключення конкурує з нашими запитами (sock=None під час connect) і може залишити зайве з'єднання.
    """

    def __init__(self, connect: Connector, sleep: Callable[[float], None],
                 decode: Callable[[ModbusClient], Reading] = read_reading, reconnect_delay: float = 1.0) -> None:
        self._connect = connect
        self._decode = decode
        self._sleep = sleep
        self._reconnect_delay = reconnect_delay
        self._client: ModbusClient | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None

    def read(self) -> Reading:
        """Raises: один із LINK_ERRORS, якщо інвертор недоступний."""
        reused = self._client is not None
        try:
            return self._read_once()
        except LINK_ERRORS as e:
            self.close()
            if not reused:
                raise
            log.info("↻ логер розірвав з'єднання (%s), перепідключаюсь", describe_error(e))
        self._sleep(self._reconnect_delay)
        try:
            return self._read_once()
        except LINK_ERRORS:
            self.close()
            raise

    def close(self) -> None:
        if self._client is not None:
            with suppress(*LINK_ERRORS):
                self._client.disconnect()
            self._client = None

    def _read_once(self) -> Reading:
        if self._client is None:
            self._client = self._connect()
        return self._decode(self._client)
