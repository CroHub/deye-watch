"""Командний рядок: python -m deye <команда>.

Команди:
  info            поточний стан (типова команда)
  watch [sec]     опитувати кожні sec (типово 30) і повідомляти про зміну стану мережі;
                  у Telegram-боті працюють /info, /stop, а власнику — /users, /remove
  live [sec]      живий дашборд, оновлюється кожні sec (типово 5)
  dump START END  сирі регістри
  tg              перевірити Telegram: показати користувачів і надіслати тестове повідомлення власнику

Telegram: змінні оточення TELEGRAM_TOKEN і TELEGRAM_ADMIN, див. .env.example.
"""
import argparse
import sys
from collections.abc import Sequence
from contextlib import closing, suppress

from deye.app import build_bot_api, build_link, build_watcher
from deye.clock import Clock, SystemClock
from deye.config import ConfigError, Settings
from deye.inverter import LINK_ERRORS, describe_error, dump_registers, solarman_connector
from deye.inverter.registers import s16
from deye.logs import setup_logging
from deye.render import TerminalReport
from deye.storage import UserStore
from deye.telegram import TelegramBot

_CLEAR_SCREEN = "\033[2J\033[H"


def cmd_info(settings: Settings, clock: Clock, _args: argparse.Namespace) -> None:
    with closing(build_link(settings, clock)) as link:
        print(_terminal_report(settings, clock).render(link.read()))


def cmd_live(settings: Settings, clock: Clock, args: argparse.Namespace) -> None:
    report = _terminal_report(settings, clock)
    lo, hi = sys.maxsize, 0
    with closing(build_link(settings, clock)) as link:
        while True:
            try:
                r = link.read()
                lo, hi = min(lo, r.load_w), max(hi, r.load_w)
                print(_CLEAR_SCREEN + report.render(r, f"   (навантаження min {lo} / max {hi} W)"))
            except LINK_ERRORS as e:
                print("! помилка читання:", describe_error(e))
            clock.sleep(args.interval)


def cmd_dump(settings: Settings, _clock: Clock, args: argparse.Namespace) -> None:
    client = solarman_connector(settings.inverter)()
    try:
        for addr, value in dump_registers(client, args.start, args.end):
            print(f"{addr:5d}  {value:6d}  {s16(value):7d}  0x{value:04X}")
    finally:
        client.disconnect()


def cmd_watch(settings: Settings, clock: Clock, args: argparse.Namespace) -> None:
    link = build_link(settings, clock)
    api = build_bot_api(settings)
    build_watcher(settings, interval=args.interval, link=link, api=api, clock=clock).run()


def cmd_tg(settings: Settings, clock: Clock, _args: argparse.Namespace) -> None:
    api = build_bot_api(settings)
    if api is None:
        print("Немає TELEGRAM_TOKEN. Створи бота через @BotFather і впиши токен у .env")
        return
    bot = TelegramBot(api)
    username = bot.me()["username"]
    print(f"бот: @{username}")
    users = UserStore(settings.users_file)
    if not len(users):
        print(f"Користувачів ще немає: напиши боту @{username} (працює, коли запущено watch)")
        return
    for chat_id, name in users:
        print(f"  {name}  (chat_id {chat_id})")
    admin = settings.telegram.admin
    if not admin:
        print("TELEGRAM_ADMIN не задано — тестове повідомлення нікому надсилати")
        return
    bot.send(admin, f"✅ Deye: тестове повідомлення ({clock.now():%H:%M:%S})")
    print("не вдалося надіслати" if bot.pending else f"надіслано власнику ({users.name(admin, admin)})")


def _terminal_report(settings: Settings, clock: Clock) -> TerminalReport:
    return TerminalReport(settings.battery, settings.tariff, clock, color=sys.stdout.isatty())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deye", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("info", aliases=["snap"], help="поточний стан").set_defaults(func=cmd_info)
    watch = sub.add_parser("watch", help="стежити і сповіщати")
    watch.add_argument("interval", nargs="?", type=int, default=30)
    watch.set_defaults(func=cmd_watch)
    live = sub.add_parser("live", help="живий дашборд")
    live.add_argument("interval", nargs="?", type=int, default=5)
    live.set_defaults(func=cmd_live)
    dump = sub.add_parser("dump", help="сирі регістри")
    dump.add_argument("start", type=int)
    dump.add_argument("end", type=int)
    dump.set_defaults(func=cmd_dump)
    sub.add_parser("tg", help="перевірити Telegram").set_defaults(func=cmd_tg)
    parser.set_defaults(func=cmd_info)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        setup_logging(settings.tz)
        with suppress(KeyboardInterrupt):
            args.func(settings, SystemClock(settings.tz), args)
    except ConfigError as e:
        sys.exit(f"Помилка налаштувань: {e}")
