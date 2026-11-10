"""Журнал у stdout з місцевим часом (контейнер працює в UTC)."""
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo


class _LocalTimeFormatter(logging.Formatter):
    def __init__(self, tz: ZoneInfo) -> None:
        super().__init__("%(asctime)s  %(message)s")
        self._tz = tz

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        return datetime.fromtimestamp(record.created, self._tz).strftime(datefmt or "%Y-%m-%d %H:%M:%S")


def setup_logging(tz: ZoneInfo) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_LocalTimeFormatter(tz))
    root = logging.getLogger("deye")
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False
