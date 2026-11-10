"""Спільні фікстури: фейковий інвертор, фейковий Telegram API, керований годинник.

Залежності передаються в конструктори (а не підміняються mock.patch), тож тести не знають про внутрішні модулі.
"""
import contextlib
import io
import itertools
import json
import logging
import tempfile
import time
import unittest
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from deye.app import build_watcher
from deye.config import Settings, TelegramConfig
from deye.inverter import Link
from deye.model import Reading
from deye.telegram import Message

ADMIN, USER = "1", "2"
TZ = ZoneInfo("Europe/Kyiv")

READING = Reading(
    state=2, grid_on=True, grid_v=230.0, grid_hz=50.0, grid_w=300, grid_a=1.3, load_w=250, load_v=230.0,
    inv_w=0, soc=90, batt_v=54.0, batt_a=0.0, batt_w=0, batt_t=20.0, t_heat=30.0, t_trans=40.0,
    day_chg=1.0, day_dis=0.5, day_buy=2.0, day_load=3.0,
)


def reading(**kw: Any) -> Reading:
    return replace(READING, **kw)


def msg(chat_id: str, text: str, **kw: Any) -> Message:
    return Message(chat_id, text, f"@user{chat_id}", **kw)


class FakeClock:
    """monotonic() щоразу +step с, щоб паузи минали миттєво; sleep() нічого не робить."""

    def __init__(self, step: int = 10) -> None:
        self._ticks = itertools.count(step=step)
        self.slept: list[float] = []

    def time(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return float(next(self._ticks))

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def now(self) -> datetime:
        return datetime.now(TZ)


class FakeConn:
    def __init__(self) -> None:
        self.closed = False
        self.fail_disconnect = False

    def read_holding_registers(self, register_addr: int, quantity: int) -> list[int]:
        raise NotImplementedError

    def disconnect(self) -> None:
        self.closed = True
        if self.fail_disconnect:
            raise OSError("disconnect failed")


class Inverter:
    """connect() видає нові FakeConn; decode() бере наступну дію: Reading або виняток."""

    def __init__(self, actions: list, connect_errors: list | None = None) -> None:
        self.actions: list[Reading | BaseException] = list(actions)
        self.connect_errors = list(connect_errors or [])
        self.conns: list[FakeConn] = []

    def connect(self) -> FakeConn:
        if self.connect_errors and (err := self.connect_errors.pop(0)) is not None:
            raise err
        conn = FakeConn()
        self.conns.append(conn)
        return conn

    def decode(self, _conn: Any) -> Reading:
        if not self.actions:
            raise KeyboardInterrupt  # сценарій вичерпано — зупиняємо watch
        action = self.actions.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action

    def link(self, clock: FakeClock) -> Link:
        return Link(self.connect, sleep=clock.sleep, decode=self.decode)


@dataclass
class Sent:
    chat_id: str
    text: str
    silent: bool
    html: bool
    buttons: list[tuple[str, str]]


class FakeApi:
    """Записує sendMessage у sent, інші виклики — у calls; getUpdates бере повідомлення з inbox()."""

    def __init__(self) -> None:
        self.sent: list[Sent] = []
        self.calls: list[tuple[str, dict]] = []
        self.error: Exception | None = None  # якщо задано — кожен виклик кидає його
        self.updates: list[dict] | None = None  # сирі оновлення для getUpdates замість inbox()
        self.inbox: Callable[[], list[Message]] = list
        self._update_ids = itertools.count(1)

    def call(self, method: str, params: Any = None, timeout: int = 10) -> dict:
        if self.error:
            raise self.error
        params = dict(params or {})
        if method == "sendMessage":
            markup = json.loads(params["reply_markup"])["inline_keyboard"] if "reply_markup" in params else []
            self.sent.append(Sent(str(params["chat_id"]), params["text"], bool(params["disable_notification"]),
                                  params.get("parse_mode") == "HTML",
                                  [(row[0]["text"], row[0]["callback_data"]) for row in markup]))
            return {"ok": True, "result": {}}
        self.calls.append((method, params))
        if method == "getUpdates":
            if self.updates is not None:
                return {"ok": True, "result": self.updates}
            return {"ok": True, "result": [self._update(m) for m in self.inbox()]}
        return {"ok": True, "result": []}

    def _update(self, m: Message) -> dict:
        author = {"username": m.sender.lstrip("@")}
        chat = {"id": int(m.chat_id)}
        if m.callback_id:
            return {"update_id": next(self._update_ids), "callback_query": {
                "id": m.callback_id, "from": author, "data": m.text,
                "message": {"message_id": m.message_id, "chat": chat}}}
        return {"update_id": next(self._update_ids), "message": {"chat": chat, "from": author, "text": m.text}}


def http_error(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(body))  # type: ignore[arg-type]


class BotTestCase(unittest.TestCase):
    """Тимчасовий DATA_DIR з users.json і фейковий Telegram."""

    users: ClassVar[dict[str, str]] = {ADMIN: "Roman", USER: "Яна"}

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        (self.data / "users.json").write_text(json.dumps(self.users, ensure_ascii=False))
        self.settings = Settings(data_dir=self.data, telegram=TelegramConfig(token="test", admin=ADMIN))
        self.api = FakeApi()
        logging.disable(logging.CRITICAL)  # журнал сценаріїв не засмічує вивід тестів
        self.addCleanup(logging.disable, logging.NOTSET)

    @property
    def sent(self) -> list[Sent]:
        return self.api.sent

    def to(self, chat_id: str) -> list[Sent]:
        return [s for s in self.sent if s.chat_id == chat_id]

    def saved_users(self, file: str = "users.json") -> dict[str, str]:
        path = self.data / file
        users: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}
        return users

    def run_watch(self, actions: list, inbox: list[tuple[int, Message]] | None = None,
                  connect_errors: list | None = None) -> Inverter:
        """Запускає watch до вичерпання сценарію.

        inbox — (n, повідомлення): повідомлення приходить у боті, щойно інвертор «відповів» n разів
        (тобто після n-ї дії зі списку actions).
        """
        inverter = Inverter(actions, connect_errors)
        total = len(actions)
        pending = list(inbox or [])

        def deliver() -> list[Message]:
            done = total - len(inverter.actions)
            ready = [m for n, m in pending if n <= done]
            pending[:] = [(n, m) for n, m in pending if n > done]
            if not ready and not inverter.actions and not pending:
                raise KeyboardInterrupt
            return ready

        self.api.inbox = deliver
        clock = FakeClock()
        watcher = build_watcher(self.settings, interval=30, link=inverter.link(clock), api=self.api, clock=clock)
        with contextlib.suppress(KeyboardInterrupt):
            watcher.run()
        return inverter
