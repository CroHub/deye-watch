# Deye monitor

[English](README.md) · **Українська**

Легкий монітор гібридного інвертора **Deye** через Wi-Fi-логер **Solarman LSW-3** (Modbus поверх TCP, локально,
без хмари Solarman) і Telegram-бот для всієї родини:

- ⚡ сповіщення, коли світло зникає і з'являється, — з тим, скільки його не було / було;
- 🔋 попередження «АКБ скоро сяде» (один раз за розряд, без спаму) і прогноз автономії;
- 📊 `/info` — поточний стан: мережа, АКБ, навантаження, споживання за день, температури;
- 🛠 власнику окремо — службові повідомлення (втрата зв'язку з логером, нові користувачі).

Без Home Assistant: один контейнер, `docker compose up -d`.

## Сумісність

| Обладнання | Статус |
|---|---|
| Deye SUN-5K-SG03LP1 + Solarman LSW-3 | ✅ перевірено |
| Інші однофазні низьковольтні гібриди Deye (SG03LP1 / SG04LP1 / SG05LP1, 3.6–12 кВт) та їхні ребрендинги | ❔ мабуть, працюють (та сама карта регістрів), не перевірено |
| Трифазні Deye (SG01HP3, SG04LP3 …) | ❌ інша карта регістрів |

Перевірили на своєму інверторі — напишіть в issue, що працює, а що ні. Для діагностики:
`make dump` виводить сирі регістри (`make dump FROM=150 TO=194` — діапазон).

## Запуск

Потрібен лише Docker (з Compose) на машині в тій самій локальній мережі, що й логер.

```sh
cp .env.example .env       # INVERTER_HOST, INVERTER_SERIAL, TELEGRAM_TOKEN, TELEGRAM_ADMIN
make run                   # зібрати образи, прогнати тести й лінтер, запустити бот deye-watch
```

Без `make`: `docker compose up -d --build watch`.

- `INVERTER_SERIAL` — серійний номер **логера** (наліпка на LSW-3), не інвертора.
- `TELEGRAM_TOKEN` — від [@BotFather](https://t.me/BotFather); `TELEGRAM_ADMIN` — ваш chat_id
  (можна дізнатися в [@userinfobot](https://t.me/userinfobot)).
- Ємність АКБ, пороги заряду, тариф і часовий пояс — у `.env.example`.

> 🔒 Підписка — зі схваленням власника: новий користувач пише ім'я, власнику приходить запит із кнопками
> **Додати / Відхилити**. Відхилених бот далі ігнорує (`data/blocked.json` — видаліть запис, щоб дозволити
> повторний запит). Без `TELEGRAM_ADMIN` підписатися не може ніхто.

### Команди

```sh
make info                  # поточний стан інвертора (разово, з поточним кодом)
make live                  # живий дашборд (make live SEC=2)
make dump                  # сирі регістри (make dump FROM=150 TO=194)
make tg                    # перевірити Telegram: користувачі + тестове повідомлення власнику
make logs                  # логи бота
make test                  # тести (без інвертора й Telegram)
make lint                  # ruff + mypy strict
make                       # список усіх команд
```

Те саме без `make`: `docker compose run --rm cli info`, `docker compose run --rm test`,
`docker compose run --rm lint`, `docker compose logs -f watch`.

### Telegram

Новий користувач пише боту своє ім'я; щойно власник схвалить запит — почнуть приходити сповіщення.
Команди: `/info`, `/stop`; власнику ще `/users` (разом із запитами, що чекають) і `/remove`.

## Архітектура

```
deye/
  model.py          Reading (знімок стану), Battery (запас, автономія), diagnose() — чиста доменна логіка
  config.py         Settings: типові значення + змінні оточення
  clock.py          Clock — абстракція часу (у тестах — FakeClock)
  storage.py        UserStore, GridStateStore — JSON у DATA_DIR з атомарним записом
  inverter/
    registers.py    карта регістрів → Reading
    link.py         Link — постійне з'єднання з логером + одна повторна спроба після розриву
  telegram/
    api.py          TelegramApi — HTTP-транспорт Bot API
    bot.py          TelegramBot — черга надсилання на час без інтернету, прийом оновлень
    message.py      Message, parse_update()
  render/
    format.py       тривалість, шкали заряду
    terminal.py     звіт для терміналу
    telegram.py     звіт /info і тексти подій для Telegram
  watch/
    alarms.py       правила: GridAlarm, LowBatteryAlarm, LinkHealth
    notifier.py     Notifier — усім користувачам / лише власнику
    watcher.py      Monitor (одне опитування), Sleep/BotListener (пауза), Watcher (цикл)
  bot/commands.py   CommandHandler — /info, /stop, /users, /remove, реєстрація зі схваленням власника
  app.py            composition root: збирає залежності
  cli.py            командний рядок (argparse)
```

Принципи:

- **Одна відповідальність** на клас: транспорт Telegram не знає про користувачів, правила сповіщень не знають
  про Telegram (лише про `Notifier`), звіти не знають, звідки взялись дані.
- **Залежності передаються в конструктор** (`Clock`, `Connector`, `BotApi`) і збираються лише в `app.py` —
  тести підставляють фейки без `mock.patch`.
- **Нове правило сповіщень** — клас із методом `check(reading)`, доданий у список `alarms` в `app.py`;
  решту коду змінювати не треба.

## Дані

Створюються автоматично в `data/` (у git не потрапляють):

- `users.json` — підписані користувачі (chat_id → ім'я);
- `requests.json` — запити, що чекають схвалення; `blocked.json` — відхилені;
- `state.json` — останній стан мережі, щоб після перезапуску правильно рахувати, скільки світла немає/є.

## Ліцензія

[MIT](LICENSE)
