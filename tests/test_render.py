"""Розрахунки, регістри й вигляд звітів."""
import unittest

from deye.inverter import read_reading
from deye.inverter.registers import s16, temperature
from deye.model import Battery
from deye.render import TelegramTexts, TerminalReport
from deye.render.format import charge_eta, duration, emoji_bar, soc_icon
from helpers import READING, FakeClock, reading

BATTERY = Battery()


class FormatTest(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(duration(None), "—")
        self.assertEqual(duration(0), "—")
        self.assertEqual(duration(0.5), "30 хв")
        self.assertEqual(duration(2.25), "2 год 15 хв")

    def test_soc_colors(self):
        cases = {100: "🟩", 60: "🟩", 59: "🟨", 35: "🟨", 34: "🟧", 25: "🟧", 24: "🟥", 0: "🟥"}
        for soc, icon in cases.items():
            with self.subTest(soc=soc):
                self.assertEqual(soc_icon(soc), icon)

    def test_emoji_bar(self):
        self.assertEqual(emoji_bar(100), "🟩" * 10)
        self.assertEqual(emoji_bar(0), "⬜" * 10)
        self.assertEqual(emoji_bar(3), "🟥" + "⬜" * 9)  # будь-який заряд > 0 видно
        self.assertEqual(emoji_bar(59), "🟨" * 6 + "⬜" * 4)

    def test_charge_eta(self):
        self.assertEqual(charge_eta(reading(soc=100, batt_w=-50), BATTERY), "майже повна")
        self.assertEqual(charge_eta(reading(soc=50, batt_w=-500), BATTERY), "до 100 % ≈ 5 год 00 хв")
        self.assertEqual(charge_eta(reading(soc=50, batt_w=0), BATTERY), "—")


class RegistersTest(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(s16(65535), -1)
        self.assertEqual(s16(100), 100)
        self.assertEqual(temperature(1250), 25.0)

    def test_read_reading_maps_registers(self):
        class Client:
            def read_holding_registers(self, start: int, count: int) -> list[int]:
                regs = {59: 2, 70: 12, 90: 1400, 91: 1350, 150: 2301, 184: 64, 190: 65036, 194: 1}
                return [regs.get(start + i, 0) for i in range(count)]

            def disconnect(self) -> None: ...

        r = read_reading(Client())
        self.assertEqual((r.state, r.grid_on, r.grid_v, r.soc, r.batt_w), (2, True, 230.1, 64, -500))
        self.assertEqual((r.t_heat, r.t_trans, r.day_chg), (35.0, 40.0, 1.2))


class BatteryTest(unittest.TestCase):
    def test_autonomy(self):
        d = reading(soc=60, batt_w=500, load_w=400)  # (60-20)% × 5 кВт·год = 2 кВт·год
        self.assertAlmostEqual(BATTERY.reserve_kwh(d), 2.0)
        self.assertAlmostEqual(BATTERY.autonomy_h(d) or 0, 4.0)
        switching = reading(soc=60, batt_w=0, load_w=400)  # щойно зникла мережа
        self.assertIsNone(BATTERY.autonomy_h(switching))
        self.assertAlmostEqual(BATTERY.autonomy_estimate_h(switching) or 0, 5.0)

    def test_running_low_only_when_discharging(self):
        self.assertTrue(BATTERY.is_running_low(reading(soc=20, batt_w=300)))
        self.assertFalse(BATTERY.is_running_low(reading(soc=20, batt_w=-300)))


class TelegramTextsTest(unittest.TestCase):
    texts = TelegramTexts(BATTERY, 4.32, FakeClock())

    def test_grid_on_charging(self):
        text = self.texts.report(reading(soc=64, batt_w=-600))
        self.assertIn("⚡ <b>Мережа є</b>", text)
        self.assertIn("🟩" * 6 + "⬜" * 4, text)
        self.assertIn("⬆️ Заряд АКБ  600 W", text)

    def test_grid_off_shows_autonomy(self):
        text = self.texts.report(reading(grid_on=False, soc=22, batt_w=420, load_w=380))
        self.assertIn("✕ <b>Мережі немає</b>", text)
        self.assertIn("🪫 <b>22 %</b>", text)
        self.assertIn("вистачить ≈ <b>14 хв</b>", text)
        self.assertIn("⚠️ <b>АКБ скоро сяде</b>", text)

    def test_technical_warnings_only_for_admin(self):
        d = reading(state=4, t_heat=70.0)
        self.assertNotIn("⚠️", self.texts.report(d))
        admin = self.texts.report(d, admin=True)
        self.assertIn("стан інвертора: Fault", admin)
        self.assertIn("інвертор гарячий", admin)


class TerminalReportTest(unittest.TestCase):
    def test_no_color_unless_asked(self):
        self.assertNotIn("\033[", TerminalReport(BATTERY, 4.32, FakeClock()).render(READING))
        self.assertIn("\033[", TerminalReport(BATTERY, 4.32, FakeClock(), color=True).render(READING))

    def test_flows(self):
        report = TerminalReport(BATTERY, 4.32, FakeClock())
        self.assertIn("ККД заряду", report.render(reading(batt_w=-500, grid_w=800)))
        self.assertIn("автономія ≈", report.render(reading(grid_on=False, batt_w=400)))
        self.assertIn("⚠  стан інвертора: Alarm", report.render(reading(state=3)))


if __name__ == "__main__":
    unittest.main()
