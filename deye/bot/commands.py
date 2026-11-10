"""Команди Telegram-бота. Бот відкритий для всіх: перше повідомлення нового користувача — його ім'я."""
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
ASK_NAME = "👋 Привіт! Напиши своє ім'я одним повідомленням — і я надсилатиму тобі сповіщення про світло та АКБ."


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
    def __init__(self, bot: TelegramBot, *, users: UserStore, admin: str, read: Callable[[], Reading],
                 texts: TelegramTexts, notifier: Notifier) -> None:
        self._bot = bot
        self._users = users
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
        elif msg.chat_id not in self._users:
            self._register(msg)
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

    def _register(self, msg: Message) -> None:
        """Перше повідомлення нового користувача — його ім'я (команди на кшталт /start не рахуються)."""
        if not msg.text or msg.text.startswith("/"):
            self._bot.send(msg.chat_id, ASK_NAME)
            return
        name = " ".join(msg.text.split())[:MAX_NAME]
        self._users.add(msg.chat_id, name)
        self._bot.send(msg.chat_id, f"Приємно познайомитись, {name}! Тепер ти отримуватимеш сповіщення.\n\n{HELP}")
        self._notifier.admin(f"👤 новий користувач бота: {name} ({msg.sender}, chat_id {msg.chat_id})")

    def _stop(self, msg: Message) -> None:
        name = self._users.remove(msg.chat_id)
        self._bot.send(msg.chat_id, "🔕 Сповіщення вимкнено. Щоб повернутися — напиши боту будь-що.")
        if self._is_admin(msg.chat_id):
            log.info("власник відписався від сповіщень")
        else:
            self._notifier.admin(f"🔕 {name} ({msg.sender}) — відписка від сповіщень")

    def _list_users(self, msg: Message) -> None:
        lines = [f"👥 <b>Користувачі: {len(self._users)}</b>"]
        lines += [f"• {html.escape(name)}{' (ти)' if self._is_admin(cid) else ''}  <code>{cid}</code>"
                  for cid, name in self._users]
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
        result = self._remove_one(others, arg)
        if msg.is_button:
            self._bot.answer_button(msg, result)
        else:
            self._bot.send(msg.chat_id, result)

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
