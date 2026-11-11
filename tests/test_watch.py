"""watch(): кому і які повідомлення йдуть — події світла, АКБ, зв'язку, /info."""
import json
import queue
import time
import unittest

from pysolarmanv5 import NoSocketAvailableError

from helpers import ADMIN, READING, USER, BotTestCase, msg, reading


class GridEventsTest(BotTestCase):
    def test_startup_message_goes_to_admin_only_silently(self):
        self.run_watch([READING])
        self.assertEqual(self.to(USER), [])
        [start] = self.to(ADMIN)
        self.assertIn("стежу за мережею", start.text)
        self.assertTrue(start.silent)

    def test_grid_lost_and_restored_go_to_everyone_loudly(self):
        self.run_watch([READING, reading(grid_on=False, batt_w=0), reading(grid_on=True)])
        for chat in (ADMIN, USER):
            events = [s for s in self.to(chat) if "Світло" in s.text]
            self.assertEqual(len(events), 2, chat)
            self.assertIn("Світло зникло", events[0].text)
            self.assertIn("вистачить ≈", events[0].text)  # оцінка навіть коли АКБ ще не почала віддавати
            self.assertIn("Світло з'явилось", events[1].text)
            self.assertTrue(all(not e.silent and e.html for e in events))

    def test_no_event_when_grid_unchanged(self):
        self.run_watch([READING, READING, READING])
        self.assertEqual(self.to(USER), [])

    def test_grid_state_survives_restart(self):
        since = time.time() - 2 * 3600
        (self.data / "state.json").write_text(json.dumps({"grid_on": False, "since": since}))
        self.run_watch([reading(grid_on=False), reading(grid_on=True)])
        self.assertIn("НЕМАЄ вже 2 год", self.to(ADMIN)[0].text)
        restored = [s for s in self.to(USER) if "Світло з'явилось" in s.text]
        self.assertIn("не було 2 год", restored[0].text)
        self.assertTrue(json.loads((self.data / "state.json").read_text())["grid_on"])

    def test_info_shows_how_long_grid_is_in_current_state(self):
        since = time.time() - 3 * 86400 - 5 * 3600
        (self.data / "state.json").write_text(json.dumps({"grid_on": True, "since": since}))
        # /info читає інвертор сам, тож дії чергуються: опитування, /info, опитування, /info
        self.run_watch([READING, READING, reading(grid_on=False), reading(grid_on=False)],
                       inbox=[(1, msg(USER, "/info")), (3, msg(USER, "/info"))])
        on, off = [s.text for s in self.to(USER) if "Мереж" in s.text]
        self.assertIn("світло є вже 3 д 5 год", on)
        self.assertIn("світла немає вже 0 хв", off)


class LowBatteryTest(BotTestCase):
    def test_low_battery_warns_everyone_once_per_discharge(self):
        off = dict(grid_on=False, batt_w=400)
        self.run_watch([reading(soc=30, **off), reading(soc=24, **off), reading(soc=23, **off),
                        reading(soc=22, grid_on=True, batt_w=-900), reading(soc=31, grid_on=True, batt_w=-900),
                        reading(soc=24, **off)])
        for chat in (ADMIN, USER):
            warnings = [s for s in self.to(chat) if "АКБ сідає" in s.text]
            self.assertEqual(len(warnings), 2, chat)  # раз до підзарядки вище LOW_SOC_RESET і ще раз після
            self.assertFalse(warnings[0].silent)

    def test_no_warning_while_charging(self):
        self.run_watch([reading(soc=22, batt_w=-500)])
        self.assertFalse(any("АКБ сідає" in s.text for s in self.sent))


class LinkAlertsTest(BotTestCase):
    def link_messages(self, chat: str) -> list[str]:
        return [s.text for s in self.to(chat) if "зв'яз" in s.text]

    def test_single_drop_is_healed_silently(self):
        self.run_watch([READING, NoSocketAvailableError("Connection already closed."), READING, READING])
        self.assertEqual(self.link_messages(ADMIN), [])

    def test_short_outage_below_threshold_is_only_logged(self):
        # перший невдалий поллінг = 2 помилки (старе з'єднання + повтор), далі по одній
        fails = [OSError("x")] * (self.settings.link_fails_to_report)
        self.run_watch([READING, *fails, READING])
        self.assertEqual(self.link_messages(ADMIN), [])

    def test_long_outage_alerts_admin_once_and_reports_recovery(self):
        fails = [OSError("x")] * (self.settings.link_fails_to_report + 2)
        self.run_watch([READING, *fails, READING, READING])
        texts = self.link_messages(ADMIN)
        self.assertEqual(len([t for t in texts if "немає зв'язку" in t]), 1)
        self.assertEqual(len([t for t in texts if "відновлено" in t]), 1)
        self.assertEqual(self.link_messages(USER), [])


class InfoCommandTest(BotTestCase):
    def test_info_after_logger_drop_returns_data(self):
        self.run_watch([READING, NoSocketAvailableError("Connection already closed."), READING, READING],
                       inbox=[(1, msg(USER, "/info"))])
        [report] = self.to(USER)
        self.assertIn("Мережа є", report.text)
        self.assertTrue(report.html)

    def test_info_hides_technical_warnings_from_users(self):
        hot = reading(state=3, t_heat=70.0)
        self.run_watch([READING, hot, hot], inbox=[(1, msg(USER, "/info")), (2, msg(ADMIN, "/info"))])
        [user_report] = self.to(USER)
        admin_report = next(s for s in self.to(ADMIN) if "Deye 5K" in s.text)
        self.assertNotIn("⚠️", user_report.text)
        self.assertIn("інвертор гарячий", admin_report.text)
        self.assertIn("Alarm", admin_report.text)

    def test_info_failure_user_gets_friendly_text_admin_gets_reason(self):
        self.run_watch([READING, queue.Empty(), queue.Empty(), READING], inbox=[(1, msg(USER, "/info"))])
        [reply] = self.to(USER)
        self.assertIn("не вдалося отримати дані", reply.text)
        self.assertNotIn("тайм-аут", reply.text)
        self.assertTrue(any("/info для Яна не вдався: тайм-аут відповіді" in s.text for s in self.to(ADMIN)))

    def test_info_failure_admin_sees_reason_directly(self):
        self.run_watch([READING, queue.Empty(), queue.Empty(), READING], inbox=[(1, msg(ADMIN, "/info"))])
        self.assertTrue(any(s.text.endswith("тайм-аут відповіді") for s in self.to(ADMIN)))


if __name__ == "__main__":
    unittest.main()
