"""Telegram-бот: реєстрація, /stop, /users, /remove, черга надсилання, розбір оновлень."""
import json
import unittest
import urllib.error
from dataclasses import replace
from typing import ClassVar

from deye.bot.commands import MAX_NAME
from deye.config import TelegramConfig
from deye.telegram import Message, TelegramBot
from helpers import ADMIN, READING, USER, BotTestCase, http_error, msg, reading

NEW = "3"


class RegistrationTest(BotTestCase):
    def request(self, *texts: str) -> None:
        self.run_watch([READING, READING], inbox=[(1, msg(NEW, t)) for t in texts])

    def test_start_asks_for_name_then_name_becomes_request(self):
        self.request("/start", "  Олена   Петрівна ")
        ask, sent = self.to(NEW)
        self.assertIn("Напиши своє ім'я", ask.text)
        self.assertIn("Запит надіслано власнику", sent.text)
        self.assertNotIn(NEW, self.saved_users())
        self.assertEqual(self.saved_users("requests.json")[NEW], "Олена Петрівна")

    def test_request_goes_to_admin_with_buttons(self):
        self.request("Олена")
        [req] = [s for s in self.to(ADMIN) if s.buttons]
        self.assertIn("Олена", req.text)
        self.assertEqual(req.buttons, [("✅ Додати", f"/approve {NEW}"), ("❌ Відхилити", f"/reject {NEW}")])
        self.assertFalse(any("Олена" in s.text for s in self.to(USER)))

    def test_pending_user_gets_no_alerts_and_cannot_spam_admin(self):
        self.run_watch([READING, READING, reading(grid_on=False)],
                       inbox=[(1, msg(NEW, "Олена")), (1, msg(NEW, "/info")), (1, msg(NEW, "Олена"))])
        self.assertEqual(len([s for s in self.to(ADMIN) if s.buttons]), 1)
        self.assertTrue(all("Світло" not in s.text for s in self.to(NEW)))
        self.assertEqual(sum("Запит уже надіслано" in s.text for s in self.to(NEW)), 2)

    def test_approve_button_subscribes_user(self):
        press = msg(ADMIN, f"/approve {NEW}", callback_id="cq1", message_id=55)
        self.run_watch([READING, READING, reading(grid_on=False)], inbox=[(1, msg(NEW, "Олена")), (2, press)])
        self.assertEqual(self.saved_users()[NEW], "Олена")
        self.assertEqual(self.saved_users("requests.json"), {})
        self.assertTrue(any("Запит підтверджено" in s.text for s in self.to(NEW)))
        self.assertTrue(any("Світло зникло" in s.text for s in self.to(NEW)))
        edit = dict(self.api.calls)["editMessageText"]
        self.assertEqual((edit["message_id"], edit["text"]), (55, "✅ Олена — додано."))

    def test_reject_blocks_further_requests(self):
        press = msg(ADMIN, f"/reject {NEW}", callback_id="cq1", message_id=55)
        self.run_watch([READING, READING, READING],
                       inbox=[(1, msg(NEW, "Олена")), (2, press), (3, msg(NEW, "Олена знову"))])
        self.assertNotIn(NEW, self.saved_users())
        self.assertEqual(self.saved_users("blocked.json")[NEW], "Олена")
        self.assertIn("відхилив", self.to(NEW)[-1].text)  # після відмови бот мовчить
        self.assertEqual(len([s for s in self.to(ADMIN) if s.buttons]), 1)

    def test_second_press_on_handled_request(self):
        inbox = [(1, msg(NEW, "Олена")), (2, msg(ADMIN, f"/approve {NEW}")), (2, msg(ADMIN, f"/reject {NEW}"))]
        self.run_watch([READING, READING, READING], inbox=inbox)
        self.assertIn(NEW, self.saved_users())
        self.assertTrue(any("уже оброблено" in s.text for s in self.to(ADMIN)))

    def test_only_admin_can_approve(self):
        self.run_watch([READING, READING, READING], inbox=[(1, msg(NEW, "Олена")), (2, msg(USER, f"/approve {NEW}"))])
        self.assertNotIn(NEW, self.saved_users())

    def test_admin_registers_without_approval(self):
        self.run_watch([READING, READING, READING],
                       inbox=[(1, msg(ADMIN, "/stop")), (2, msg(ADMIN, "Roman"))])
        self.assertEqual(self.saved_users()[ADMIN], "Roman")

    def test_without_admin_registration_is_closed(self):
        self.settings = replace(self.settings, telegram=TelegramConfig(token="test"))
        self.request("Олена")
        self.assertEqual(self.to(NEW)[-1].text, "Реєстрацію закрито.")
        self.assertEqual(self.saved_users("requests.json"), {})

    def test_users_shows_pending_requests(self):
        self.run_watch([READING, READING, READING], inbox=[(1, msg(NEW, "Олена")), (2, msg(ADMIN, "/users"))])
        listing = next(s for s in self.to(ADMIN) if "Користувачі" in s.text)
        self.assertIn("Чекають на схвалення: 1", listing.text)

    def test_long_name_is_truncated(self):
        self.request("А" * 100)
        self.assertEqual(len(self.saved_users("requests.json")[NEW]), MAX_NAME)


class StopTest(BotTestCase):
    def test_stop_unsubscribes_and_tells_admin(self):
        self.run_watch([READING, READING, reading(grid_on=False)], inbox=[(1, msg(USER, "/stop@deye151Bot"))])
        self.assertNotIn(USER, self.saved_users())
        self.assertIn("Сповіщення вимкнено", self.to(USER)[0].text)
        self.assertFalse(any("Світло зникло" in s.text for s in self.to(USER)))
        self.assertTrue(any("відписка" in s.text for s in self.to(ADMIN)))

    def test_coming_back_after_stop_needs_approval_again(self):
        self.run_watch([READING, READING, READING],
                       inbox=[(1, msg(USER, "/stop")), (2, msg(USER, "/start")), (2, msg(USER, "Яна"))])
        self.assertNotIn(USER, self.saved_users())
        self.assertEqual(self.saved_users("requests.json")[USER], "Яна")


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
