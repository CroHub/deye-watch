# Deye monitor

**English** · [Українська](README.uk.md)

A lightweight monitor for **Deye** hybrid inverters via the **Solarman LSW-3** Wi-Fi logger (Modbus over TCP,
fully local — no Solarman cloud), plus a Telegram bot for the whole household:

- ⚡ alerts when grid power goes out and comes back, with how long it was off / on;
- 🔋 a "battery running low" warning (once per discharge, no spam) and an autonomy estimate;
- 📊 `/info` — live status: grid, battery, load, today's energy, temperatures;
- 🛠 separate service messages for the owner (logger link lost, new users).

No Home Assistant needed: one container, `docker compose up -d`.

> The bot's texts are in Ukrainian for now. Translations are welcome — all user-facing strings live in
> `deye/render/` and `deye/bot/commands.py`.

## Compatibility

| Hardware | Status |
|---|---|
| Deye SUN-5K-SG03LP1 + Solarman LSW-3 | ✅ tested |
| Other single-phase low-voltage Deye hybrids (SG03LP1 / SG04LP1 / SG05LP1, 3.6–12 kW) and rebrands | ❔ likely (same register map), untested |
| Three-phase Deye (SG01HP3, SG04LP3 …) | ❌ different register map |

Please open an issue with what works on your hardware. For diagnostics, `make dump` prints raw registers
(`make dump FROM=150 TO=194` for a range).

## Quick start

All you need is Docker (with Compose) on a machine in the same LAN as the logger.

```sh
cp .env.example .env       # INVERTER_HOST, INVERTER_SERIAL, TELEGRAM_TOKEN, TELEGRAM_ADMIN
make run                   # build images, run tests and lint, start the deye-watch bot
```

Without `make`: `docker compose up -d --build watch`.

- `INVERTER_SERIAL` is the **logger's** serial number (sticker on the LSW-3), not the inverter's.
- `TELEGRAM_TOKEN` comes from [@BotFather](https://t.me/BotFather); `TELEGRAM_ADMIN` is your chat_id
  (e.g. from [@userinfobot](https://t.me/userinfobot)).
- Battery capacity, SOC thresholds, tariff and timezone are in `.env.example`.

> ⚠️ The bot is open: anyone who finds it in Telegram and sends a name gets alerts and can use `/info`.
> The owner is notified about every new user and can drop them with `/remove`.

### Commands

```sh
make info                  # current inverter status (one-off, with the current code)
make live                  # live dashboard (make live SEC=2)
make dump                  # raw registers (make dump FROM=150 TO=194)
make tg                    # check Telegram: list users, send a test message to the owner
make logs                  # bot logs
make test                  # tests (no inverter or Telegram needed)
make lint                  # ruff + mypy strict
make                       # list all targets
```

Same without `make`: `docker compose run --rm cli info`, `docker compose run --rm test`,
`docker compose run --rm lint`, `docker compose logs -f watch`.

### Telegram

A new user sends the bot their name and starts receiving alerts. Commands: `/info`, `/stop`;
the owner also has `/users` and `/remove`.

## Architecture

```
deye/
  model.py          Reading (snapshot), Battery (reserve, autonomy), diagnose() — pure domain logic
  config.py         Settings: defaults + environment variables
  clock.py          Clock abstraction (FakeClock in tests)
  storage.py        UserStore, GridStateStore — JSON in DATA_DIR with atomic writes
  inverter/
    registers.py    register map → Reading
    link.py         Link — persistent logger connection + one retry after the logger drops it
  telegram/
    api.py          TelegramApi — Bot API HTTP transport
    bot.py          TelegramBot — send queue that survives internet outages, update polling
    message.py      Message, parse_update()
  render/
    format.py       durations, charge bars
    terminal.py     terminal report
    telegram.py     /info report and event texts for Telegram
  watch/
    alarms.py       rules: GridAlarm, LowBatteryAlarm, LinkHealth
    notifier.py     Notifier — everyone / owner only
    watcher.py      Monitor (one poll), Sleep/BotListener (pause), Watcher (loop)
  bot/commands.py   CommandHandler — /info, /stop, /users, /remove, registration
  app.py            composition root: wires dependencies
  cli.py            command line (argparse)
```

- **One responsibility per class**: the Telegram transport knows nothing about users, alarm rules know only
  `Notifier`, not Telegram, reports don't know where the data came from.
- **Dependencies are injected** (`Clock`, `Connector`, `BotApi`) and wired only in `app.py` — tests use fakes,
  no `mock.patch`.
- **A new alert rule** is a class with `check(reading)` added to the `alarms` list in `app.py`; nothing else changes.

Code comments are in Ukrainian.

## Data

`data/users.json` — bot users (chat_id → name); `data/state.json` — last grid state, so the outage timer survives
restarts.

## License

[MIT](LICENSE)
