"""Settings.from_env: типові значення, перевизначення з .env і зрозумілі помилки."""
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

from deye.config import ConfigError, InverterConfig, Settings
from deye.inverter import solarman_connector


class FromEnvTest(unittest.TestCase):
    def test_defaults_when_env_is_empty(self):
        s = Settings.from_env({})
        self.assertEqual(s, Settings())

    def test_blank_values_mean_default(self):
        self.assertEqual(Settings.from_env({"BATTERY_KWH": "  ", "TZ": ""}), Settings())

    def test_overrides(self):
        s = Settings.from_env({
            "INVERTER_HOST": "10.0.0.7", "INVERTER_SERIAL": "1234567890", "INVERTER_PORT": "9000",
            "BATTERY_KWH": "10.24", "BATTERY_MIN_SOC": "15", "BATTERY_LOW_SOC": "20", "BATTERY_LOW_SOC_RESET": "35",
            "TELEGRAM_TOKEN": "t", "TELEGRAM_ADMIN": "42", "DATA_DIR": "/tmp/deye", "TZ": "Europe/Warsaw",
            "TARIFF": "2.5",
        })
        self.assertEqual((s.inverter.host, s.inverter.serial, s.inverter.port), ("10.0.0.7", 1234567890, 9000))
        self.assertEqual((s.battery.capacity_kwh, s.battery.min_soc, s.battery.low_soc, s.battery.low_soc_reset),
                         (10.24, 15, 20, 35))
        self.assertEqual((s.telegram.token, s.telegram.admin), ("t", "42"))
        self.assertEqual(s.data_dir, Path("/tmp/deye"))
        self.assertEqual(s.tz, ZoneInfo("Europe/Warsaw"))
        self.assertEqual(s.tariff, 2.5)

    def test_bad_value_names_the_variable(self):
        for name, value in (("INVERTER_SERIAL", "abc"), ("BATTERY_KWH", "5kWh"), ("TZ", "Mars/Olympus")):
            with self.subTest(name=name), self.assertRaisesRegex(ConfigError, name):
                Settings.from_env({name: value})


class InverterRequiredTest(unittest.TestCase):
    def test_connector_requires_host_and_serial(self):
        with self.assertRaisesRegex(ConfigError, "INVERTER_HOST, INVERTER_SERIAL"):
            solarman_connector(InverterConfig())
        with self.assertRaisesRegex(ConfigError, "INVERTER_SERIAL"):
            solarman_connector(InverterConfig(host="10.0.0.7"))

    def test_connector_is_lazy(self):
        solarman_connector(InverterConfig(host="10.0.0.7", serial=1))  # не підключається, поки не викличуть
