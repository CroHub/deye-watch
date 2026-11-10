"""Команди Telegram-бота.

Підписка — зі схваленням власника: перше повідомлення нового користувача — його ім'я, власнику приходить
запит із кнопками «Додати / Відхилити». Відхилені більше не можуть надсилати запити (data/blocked.json).
"""
import html
import logging
from collections.abc import Callable
from dataclasses import dataclass

from deye.inverter import LINK_ERRORS, describe_error
from deye.model import Reading
from deye.render import TelegramTexts
from deye.storage import UserStore
from deye.telegram import Message, TelegramBot
from deye.watch import Notifier

log = logging.getLogger(__name__)

INFO_COMMANDS = frozenset({"/info", "info", "інфо"})
MAX_NAME = 40
USER_MENU = [("info", "поточний стан інвертора"), ("stop", "відписатися від сповіщень")]
ADMIN_MENU = [*USER_MENU, ("users", "список користувачів"), ("remove", "видалити користувача")]
HELP = "Команди:\n/info — поточний стан інвертора\n/stop — відписатися від сповіщень"
HELP_ADMIN = HELP + "\n/users — список користувачів\n/remove — видалити користувача (кнопками або /remove ім'я)"
ASK_NAME = ("👋 Привіт! Напиши своє ім'я одним повідомленням — і я надішлю власнику запит "
            "на сповіщення про світло та АКБ.")
REQUEST_SENT = "Дякую, {name}! Запит надіслано власнику — щойно його підтвердять, почнуть приходити сповіщення."
REQUEST_PENDING = "⏳ Запит уже надіслано, чекай підтвердження власника."
REGISTRATION_CLOSED = "Реєстрацію закрито."
WELCOME = "✅ Вітаю, {name}! Запит підтверджено — тепер ти отримуватимеш сповіщення.\n\n" + HELP
REJECTED = "🚫 Власник відхилив запит на сповіщення."


@dataclass(frozen=True)
class Command:
    name: str  # «/info», без @botname, у нижньому регістрі
    arg: str

    @classmethod
    def parse(cls, text: str) -> "Command":
        parts = text.split(maxsplit=1)
        name = parts[0].split("@")[0].lower() if parts else ""
        return cls(name, parts[1].strip() if len(parts) > 1 else "")


class CommandHandler:
    def __init__(self, bot: TelegramBot, *, users: UserStore, requests: UserStore, blocked: UserStore, admin: str,
                 read: Callable[[], Reading], texts: TelegramTexts, notifier: Notifier) -> None:
        self._bot = bot
        self._users = users
        self._requests = requests  # чекають на схвалення власника
        self._blocked = blocked  # відхилені: їхні повідомлення ігноруємо
        self._admin = admin
        self._read = read
        self._texts = texts
        self._notifier = notifier

    def setup_menu(self) -> None:
        """Меню команд: спільне для всіх, а власнику — ще й адмінські."""
        self._bot.set_menu(USER_MENU)
        if self._admin:
            self._bot.set_menu(ADMIN_MENU, chat_id=self._admin)

    def handle(self, msg: Message) -> None:
        cmd = Command.parse(msg.text)
        admin = self._is_admin(msg.chat_id)
        if admin and cmd.name == "/remove":  # адмінські команди працюють і після власного /stop
            self._remove(msg, cmd.arg)
        elif admin and cmd.name == "/users":
            self._list_users(msg)
        elif admin and cmd.name in ("/approve", "/reject"):
            self._reply(msg, self._decide(cmd.arg, approve=cmd.name == "/approve"))
        elif msg.chat_id in self._blocked:
            log.info("ігнорую повідомлення від відхиленого %s (chat_id %s)", msg.sender, msg.chat_id)
        elif msg.chat_id not in self._users:
            self._register(msg, admin=admin)
        else:
            log.info("команда від %s: %s", self._users.name(msg.chat_id, msg.sender), msg.text)
            if cmd.name == "/stop":
                self._stop(msg)
            elif cmd.name in INFO_COMMANDS:
                self._info(msg)
            else:
                self._bot.send(msg.chat_id, HELP_ADMIN if admin else HELP)

    def _is_admin(self, chat_id: str) -> bool:
        return bool(self._admin) and chat_id == self._admin

    def _register(self, msg: Message, *, admin: bool) -> None:
        """Перше повідомлення нового користувача — його ім'я (команди на кшталт /start не рахуються).
        Власник підписується одразу, решта — через запит, який власник схвалює кнопкою."""
        if msg.chat_id in self._requests:
            self._bot.send(msg.chat_id, REQUEST_PENDING)
            return
        if not msg.text or msg.text.startswith("/"):
            self._bot.send(msg.chat_id, ASK_NAME)
            return
        name = " ".join(msg.text.split())[:MAX_NAME]
        if admin:
            self._users.add(msg.chat_id, name)
            self._bot.send(msg.chat_id, WELCOME.format(name=name))
        elif not self._admin:
            log.warning("запит від %s (chat_id %s) відхилено: TELEGRAM_ADMIN не задано, схвалювати нікому",
                        msg.sender, msg.chat_id)
            self._bot.send(msg.chat_id, REGISTRATION_CLOSED)
        else:
            self._requests.add(msg.chat_id, name)
            self._bot.send(msg.chat_id, REQUEST_SENT.format(name=name))
            log.info("запит на підписку: %s (%s, chat_id %s)", name, msg.sender, msg.chat_id)
            buttons = [("✅ Додати", f"/approve {msg.chat_id}"), ("❌ Відхилити", f"/reject {msg.chat_id}")]
            self._bot.send(self._admin, f"👤 Запит на сповіщення: {name} ({msg.sender}, chat_id {msg.chat_id})",
                           buttons=buttons)

    def _decide(self, chat_id: str, *, approve: bool) -> str:
        name = self._requests.remove(chat_id)
        if name is None:
            return "Цей запит уже оброблено."
        if approve:
            self._users.add(chat_id, name)
            self._bot.send(chat_id, WELCOME.format(name=name))
            log.info("власник схвалив: %s (chat_id %s)", name, chat_id)
            return f"✅ {name} — додано."
        self._blocked.add(chat_id, name)
        self._bot.send(chat_id, REJECTED)
        log.info("власник відхилив: %s (chat_id %s)", name, chat_id)
        return f"❌ {name} — відхилено, повторні запити ігноруватимуться."

    def _reply(self, msg: Message, text: str) -> None:
        """Відповідь на натискання кнопки замінює повідомлення з кнопками; на текстову команду — нове повідомлення."""
        if msg.is_button:
            self._bot.answer_button(msg, text)
        else:
            self._bot.send(msg.chat_id, text)

    def _stop(self, msg: Message) -> None:
        name = self._users.remove(msg.chat_id)
        self._bot.send(msg.chat_id, "🔕 Сповіщення вимкнено. Щоб повернутися — напиши боту своє ім'я "
                                    "(власник підтвердить запит).")
        if self._is_admin(msg.chat_id):
            log.info("власник відписався від сповіщень")
        else:
            self._notifier.admin(f"🔕 {name} ({msg.sender}) — відписка від сповіщень")

    def _list_users(self, msg: Message) -> None:
        lines = [f"👥 <b>Користувачі: {len(self._users)}</b>"]
        lines += [f"• {html.escape(name)}{' (ти)' if self._is_admin(cid) else ''}  <code>{cid}</code>"
                  for cid, name in self._users]
        if len(self._requests):
            lines.append(f"\n⏳ <b>Чекають на схвалення: {len(self._requests)}</b>")
            lines += [f"• {html.escape(name)}  <code>{cid}</code>" for cid, name in self._requests]
        self._bot.send(msg.chat_id, "\n".join(lines), html=True)

    def _remove(self, msg: Message, arg: str) -> None:
        """/remove — кнопки з користувачами; /remove <chat_id або ім'я> — видалити одразу."""
        others = {cid: name for cid, name in self._users if not self._is_admin(cid)}
        if not arg:
            if others:
                buttons = [(f"🗑 {name}", f"/remove {cid}") for cid, name in others.items()]
                self._bot.send(msg.chat_id, "Кого видалити?", buttons=buttons)
            else:
                self._bot.send(msg.chat_id, "Крім тебе, користувачів немає.")
            return
        self._reply(msg, self._remove_one(others, arg))

    def _remove_one(self, candidates: dict[str, str], arg: str) -> str:
        if self._is_admin(arg):
            return "Себе видалити не можна — для цього є /stop."
        matches = [cid for cid, name in candidates.items() if arg == cid or name.lower() == arg.lower()]
        if not matches:
            return f"Не знайшов «{arg}». Список — /users."
        if len(matches) > 1:
            return f"Кілька користувачів з ім'ям «{arg}» — видали за chat_id (див. /users)."
        name = self._users.remove(matches[0])
        log.info("адмін видалив користувача: %s (chat_id %s)", name, matches[0])
        return f"🗑 {name} видалено — сповіщення більше не приходитимуть."

    def _info(self, msg: Message) -> None:
        admin = self._is_admin(msg.chat_id)
        try:
            self._bot.send(msg.chat_id, self._texts.report(self._read(), admin=admin), html=True)
        except LINK_ERRORS as e:
            if admin:
                self._bot.send(msg.chat_id, f"⚠️ немає зв'язку з інвертором: {describe_error(e)}")
                return
            # користувачу — без технічних подробиць
            self._bot.send(msg.chat_id, "😕 Зараз не вдалося отримати дані з інвертора, спробуй за хвилину.")
            self._notifier.admin(f"⚠️ /info для {self._users.name(msg.chat_id, msg.sender)} "
                                 f"не вдався: {describe_error(e)}")
