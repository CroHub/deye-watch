# deye-watch

**English** · [Українська](README.uk.md)

A lightweight monitor for **Deye** hybrid inverters via the **Solarman LSW-3** Wi-Fi logger (Modbus over TCP,
fully local — no Solarman cloud), plus a Telegram bot for the whole household:

- ⚡ alerts when grid power goes out and comes back, with how long it was off / on;
- 🔋 a "battery running low" warning (once per discharge, no spam) and an autonomy estimate;
- 📊 `/info` — live status: grid, battery, load, today's energy, temperatures;
- 🔒 sign-ups only with the owner's approval;
- 🛠 separate service messages for the owner (logger link lost, new requests).

No Home Assistant, no cloud: one container on any always-on computer in your home network.

> The bot's texts are in Ukrainian for now. Translations are welcome — all user-facing strings live in
> `deye/render/` and `deye/bot/commands.py`.

**Contents:** [Compatibility](#compatibility) · [Getting started](#getting-started) ·
[Telegram bot](#telegram-bot) · [Commands](#commands) · [Updating](#updating) · [Architecture](#architecture)

## Compatibility

| Hardware | Status |
|---|---|
| Deye SUN-5K-SG03LP1 + Solarman LSW-3 | ✅ tested |
| Other single-phase low-voltage Deye hybrids (SG03LP1 / SG04LP1 / SG05LP1, 3.6–12 kW) and rebrands | ❔ likely (same register map), untested |
| Three-phase Deye (SG01HP3, SG04LP3 …) | ❌ different register map |

Please open an issue with what works on your hardware. For diagnostics, `make dump` prints raw registers
(`make dump FROM=150 TO=194` for a range).

## Getting started

### 1. Requirements

- An always-on computer **in the same local network as the logger**: a Linux server, Raspberry Pi, home NAS,
  an old laptop. Linux works best.
- **Docker** with Compose: <https://docs.docker.com/engine/install/> (check: `docker compose version`).
- **git** and preferably **make** (Debian/Ubuntu/Raspberry Pi OS: `sudo apt install git make`).
  `make` is optional — see [Commands](#commands).

> On macOS/Windows with Docker Desktop, enable **Settings → Resources → Network → Enable host networking**:
> the container uses the host network to reach the logger.

### 2. Get the project

```sh
git clone https://github.com/CroHub/deye-watch.git
cd deye-watch
cp .env.example .env
```

All settings live in `.env` (it is never committed).

### 3. Find the logger: IP address and serial number

- **IP address** — in your router's web UI, in the list of connected devices (the logger usually shows up as
  `ESP…`, `LSW…`, or by the MAC address from its sticker). Reserve a fixed address for it (DHCP reservation),
  otherwise it may change after a router reboot.
- **Logger serial number** — 10 digits on the LSW-3 sticker (*not* the inverter's serial!). It is also shown
  in the logger's web UI: open `http://<logger IP>` (default login `admin`, password `admin`).

Put them into `.env`:

```sh
INVERTER_HOST=192.168.1.50
INVERTER_SERIAL=2712345678
```

Check the connection — it should print the current inverter status (the first run also builds the image, ~1 min):

```sh
make info
```

### 4. Create a Telegram bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram and send `/newbot`.
2. Enter the display name, e.g. `Home power`.
3. Enter a username — Latin letters, must end with `bot`, e.g. `my_home_deye_bot`.
4. BotFather replies with a **token** like `1234567890:AAH...`. It is the bot's password — keep it secret.

Put it into `.env`:

```sh
TELEGRAM_TOKEN=1234567890:AAH...
```

Optional, in the same @BotFather chat: `/setuserpic` — avatar, `/setdescription` — the text people see before
their first message.

### 5. Make yourself the bot owner (admin)

The owner is the one Telegram account the bot trusts: it approves new users and gets service messages.
The bot recognises the owner by **chat_id** — a number you put into `.env`.

1. Open [@userinfobot](https://t.me/userinfobot) and press **Start** — it replies with your `Id`
   (e.g. `123456789`).
2. Put it into `.env`:

   ```sh
   TELEGRAM_ADMIN=123456789
   ```

Without `TELEGRAM_ADMIN` the bot runs, but nobody can subscribe — there is no one to approve requests.

### 6. Other settings (if needed)

`.env.example` lists every option with its default: battery capacity (`BATTERY_KWH`), SOC thresholds,
tariff (`TARIFF`), timezone (`TZ`). Uncomment and change the ones that differ.

### 7. Start

```sh
make run     # build images, run tests, start the bot in the background
make logs    # watch what it does (Ctrl+C leaves the logs, the bot keeps running)
```

The bot runs with `restart: unless-stopped`, so it comes back after a reboot or a Docker restart.

### 8. Subscribe

1. Find your bot in Telegram by its username and press **Start**.
2. Send your name — you are the owner, so you are subscribed right away.
3. Check: `/info` should show the inverter status.

Now you can share the bot link with your family (see below).

## Telegram bot

**How someone else subscribes.** They open the bot, press **Start** and send their name. The owner gets a
request with **✅ Approve** / **❌ Reject** buttons. Once approved, the person gets a welcome message and all
alerts. Rejected users are ignored from then on; to let one ask again, delete their entry from
`data/blocked.json`.

**Commands for everyone:** `/info` — current status, `/stop` — unsubscribe.

**Owner commands** (shown in the owner's menu only): `/users` — users and pending requests;
`/remove` — remove a user (via buttons or `/remove name`).

**Alerts:** power lost / restored — everyone; "battery running low" — everyone; logger link lost, bot start —
owner only, silently.

## Commands

```sh
make run                   # build, run tests and lint, (re)start the bot
make logs                  # bot logs
make stop                  # stop the bot
make info                  # current inverter status (one-off)
make live                  # live terminal dashboard (make live SEC=2)
make dump                  # raw registers (make dump FROM=150 TO=194)
make tg                    # check Telegram: list users, send a test message to the owner
make test                  # tests (no inverter or Telegram needed)
make lint                  # ruff + mypy strict
make                       # list all targets
```

Without `make` — the same via Docker Compose:

| make | docker compose |
|---|---|
| `make run` | `docker compose up -d --build watch` |
| `make logs` | `docker compose logs -f watch` |
| `make stop` | `docker compose down` |
| `make info` | `docker compose run --rm cli info` |
| `make test` | `docker compose run --rm test` |

## Updating

```sh
git pull
make run
```

Your data (`data/`) and settings (`.env`) are kept.

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
  bot/commands.py   CommandHandler — /info, /stop, /users, /remove, sign-up with owner approval
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

Created automatically in `data/` (not in git):

- `users.json` — subscribed users (chat_id → name);
- `requests.json` — sign-up requests awaiting approval; `blocked.json` — rejected users;
- `state.json` — last grid state, so the outage timer survives restarts.

## License

[MIT](LICENSE)
