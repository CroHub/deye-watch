"""Збирання застосунку з частин (composition root): тут і лише тут вирішується, що з чим з'єднати."""
import logging

from deye.bot import CommandHandler
from deye.clock import Clock
from deye.config import Settings
from deye.inverter import Link, solarman_connector
from deye.render import TelegramTexts
from deye.storage import GridStateStore, UserStore
from deye.telegram import BotApi, TelegramApi, TelegramBot
from deye.watch import BotListener, GridAlarm, LinkHealth, LowBatteryAlarm, Monitor, Notifier, Sleep, Watcher
from deye.watch.watcher import Pause

log = logging.getLogger(__name__)


def build_link(settings: Settings, clock: Clock) -> Link:
    return Link(solarman_connector(settings.inverter), sleep=clock.sleep,
                reconnect_delay=settings.inverter.reconnect_delay)


def build_bot_api(settings: Settings) -> BotApi | None:
    return TelegramApi(settings.telegram.token) if settings.telegram.enabled else None


def build_watcher(settings: Settings, *, interval: int, link: Link, api: BotApi | None, clock: Clock) -> Watcher:
    """watch: повідомляє про зміну наявності мережі, низький заряд АКБ і втрату зв'язку з інвертором;
    якщо налаштовано Telegram — розсилає це всім користувачам бота і відповідає на команди."""
    admin = settings.telegram.admin
    users = UserStore(settings.users_file)
    bot = TelegramBot(api) if api else None
    notifier = Notifier(bot, users, admin, clock)
    texts = TelegramTexts(settings.battery, settings.tariff, clock)

    grid = GridAlarm(GridStateStore(settings.state_file), notifier, texts, clock)
    monitor = Monitor(
        read=link.read,
        health=LinkHealth(notifier, clock, settings.link_fails_to_report),
        alarms=[
            LowBatteryAlarm(settings.battery, notifier, texts),
            grid,
        ],
    )
    pause: Pause = Sleep(clock)
    if bot and not admin:
        log.warning("TELEGRAM_ADMIN не задано — нові користувачі не зможуть підписатися (схвалювати нікому)")
    if bot:
        handler = CommandHandler(bot, users=users, requests=UserStore(settings.requests_file),
                                 blocked=UserStore(settings.blocked_file), admin=admin, read=link.read, texts=texts,
                                 notifier=notifier, grid_since=grid.since)
        handler.setup_menu()
        pause = BotListener(bot, handler.handle, clock)

    status = f"Telegram увімкнено, користувачів: {len(users)}" if bot else "Telegram вимкнено"
    log.info("стежу за мережею, опитування кожні %d с, %s (Ctrl+C — вихід)", interval, status)
    return Watcher(monitor, pause, interval)
