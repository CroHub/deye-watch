"""Telegram-бот: реєстрація, /stop, /users, /remove, черга надсилання, розбір оновлень."""
import json
import unittest
import urllib.error
from typing import ClassVar

from deye.bot.commands import MAX_NAME
from deye.telegram import Message, TelegramBot
from helpers import ADMIN, READING, USER, BotTestCase, http_error, msg, reading

NEW = "3"


class RegistrationTest(BotTestCase):
    def test_start_asks_for_name_then_name_registers(self):
        self.run_watch([READING, READING], inbox=[(1, msg(NEW, "/start")), (1, msg(NEW, "  Олена   Петрівна "))])
        ask, welcome = self.to(NEW)
        self.assertIn("Напиши своє ім'я", ask.text)
        self.assertIn("Олена Петрівна", welcome.text)
        self.assertEqual(self.saved_users()[NEW], "Олена Петрівна")

    def test_new_user_notice_goes_to_admin_only(self):
        self.run_watch([READING, READING], inbox=[(1, msg(NEW, "Олена"))])
        self.assertTrue(any("новий користувач бота: Олена" in s.text for s in self.to(ADMIN)))
        self.assertFalse(any("новий користувач" in s.text for s in self.to(USER)))

    def test_long_name_is_truncated(self):
        self.run_watch([READING, READING], inbox=[(1, msg(NEW, "А" * 100))])
        self.assertEqual(len(self.saved_users()[NEW]), MAX_NAME)


class StopTest(BotTestCase):
    def test_stop_unsubscribes_and_tells_admin(self):
        self.run_watch([READING, READING, reading(grid_on=False)], inbox=[(1, msg(USER, "/stop@deye151Bot"))])
        self.assertNotIn(USER, self.saved_users())
        self.assertIn("Сповіщення вимкнено", self.to(USER)[0].text)
        self.assertFalse(any("Світло зникло" in s.text for s in self.to(USER)))
        self.assertTrue(any("відписка" in s.text for s in self.to(ADMIN)))

    def test_writing_again_after_stop_re_registers(self):
        self.run_watch([READING, READING, READING],
                       inbox=[(1, msg(USER, "/stop")), (2, msg(USER, "/start")), (2, msg(USER, "Яна"))])
        self.assertEqual(self.saved_users()[USER], "Яна")


class AdminCommandsTest(BotTestCase):
    users: ClassVar[dict[str, str]] = {ADMIN: "Roman", USER: "Яна", "4": "Ivan"}

    def test_users_lists_everyone_for_admin(self):
        self.run_watch([READING, READING], inbox=[(1, msg(ADMIN, "/users"))])
        listing = next(s for s in self.to(ADMIN) if "Користувачі: 3" in s.text)
        self.assertIn("Roman (ти)", listing.text)
        self.assertIn("Ivan", listing.text)

    def test_users_and_remove_not_available_to_regular_users(self):
        self.run_watch([READING, READING], inbox=[(1, msg(USER, "/users")), (1, msg(USER, "/remove 1"))])
        self.assertTrue(all(s.text.startswith("Команди:") for s in self.to(USER)))
        self.assertIn(ADMIN, self.saved_users())

    def test_remove_without_arg_shows_buttons_except_admin(self):
        self.run_watch([READING, READING], inbox=[(1, msg(ADMIN, "/remove"))])
        [prompt] = [s for s in self.to(ADMIN) if s.buttons]
        self.assertEqual(prompt.buttons, [("🗑 Яна", f"/remove {USER}"), ("🗑 Ivan", "/remove 4")])

    def test_button_press_removes_and_replaces_message(self):
        press = msg(ADMIN, f"/remove {USER}", callback_id="cq1", message_id=55)
        self.run_watch([READING, READING], inbox=[(1, press)])
        self.assertNotIn(USER, self.saved_users())
        methods = dict(self.api.calls)
        self.assertEqual(methods["answerCallbackQuery"]["callback_query_id"], "cq1")
        self.assertEqual(methods["editMessageText"]["message_id"], 55)
        self.assertIn("Яна видалено", methods["editMessageText"]["text"])

    def test_remove_by_name_case_insensitive(self):
        self.run_watch([READING, READING], inbox=[(1, msg(ADMIN, "/remove ivan"))])
        self.assertNotIn("4", self.saved_users())

    def test_remove_unknown_and_self(self):
        inbox = [(1, msg(ADMIN, "/remove Петро")), (1, msg(ADMIN, f"/remove {ADMIN}"))]
        self.run_watch([READING, READING], inbox=inbox)
        texts = [s.text for s in self.to(ADMIN)]
        self.assertTrue(any("Не знайшов «Петро»" in t for t in texts))
        self.assertTrue(any("Себе видалити не можна" in t for t in texts))

    def test_admin_commands_work_after_admin_stop(self):
        self.run_watch([READING, READING, READING],
                       inbox=[(1, msg(ADMIN, "/stop")), (2, msg(ADMIN, "/users")), (2, msg(ADMIN, "/remove"))])
        texts = [s.text for s in self.to(ADMIN)]
        self.assertTrue(any("Користувачі: 2" in t for t in texts))
        self.assertTrue(any(t == "Кого видалити?" for t in texts))
        self.assertFalse(any("Напиши своє ім'я" in t for t in texts))


class TelegramBotTest(BotTestCase):
    def test_queue_holds_messages_while_offline_and_sends_in_order(self):
        bot = TelegramBot(self.api)
        self.api.error = urllib.error.URLError("no route")
        bot.send(USER, "перше")
        bot.send(USER, "друге")
        self.assertEqual(bot.pending, 2)
        self.api.error = None
        bot.flush()
        self.assertEqual([s.text for s in self.to(USER)], ["перше", "друге"])
        self.assertEqual(bot.pending, 0)

    def test_rejected_message_is_dropped_not_retried(self):
        bot = TelegramBot(self.api)
        self.api.error = http_error(403, b"bot was blocked")
        bot.send(USER, "x")
        self.assertEqual(bot.pending, 0)

    def test_receive_parses_text_and_button_presses(self):
        self.api.updates = [
            {"update_id": 10, "message": {"chat": {"id": 2}, "from": {"username": "yana"}, "text": " /info "}},
            {"update_id": 11, "message": {"chat": {"id": 2}, "from": {"first_name": "Yana"}, "sticker": {}}},
            {"update_id": 12, "callback_query": {"id": "cq", "from": {"username": "roman"}, "data": "/remove 2",
                                                 "message": {"message_id": 7, "chat": {"id": 1}}}},
        ]
        bot = TelegramBot(self.api)
        got = bot.receive(1)
        self.assertEqual(got, [Message("2", "/info", "@yana"),
                               Message("1", "/remove 2", "@roman", callback_id="cq", message_id=7)])
        bot.receive(1)
        self.assertEqual(self.api.calls[-1][1]["offset"], 13)

    def test_admin_menu_has_extra_commands(self):
        self.run_watch([READING])
        menus = [(p.get("scope"), [c["command"] for c in json.loads(p["commands"])]) for m, p in self.api.calls
                 if m == "setMyCommands"]
        self.assertEqual(menus[0], (None, ["info", "stop"]))
        self.assertEqual(json.loads(menus[1][0] or "{}")["chat_id"], int(ADMIN))
        self.assertEqual(menus[1][1], ["info", "stop", "users", "remove"])


if __name__ == "__main__":
    unittest.main()
