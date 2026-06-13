# tgchat — Telegram Parser + Bot

Мониторинг Telegram-чатов и каналов по ключевым словам с выгрузкой в Google Таблицу и управлением через Telegram-бота.

## Возможности

- Мониторинг ваших чатов/каналов по keywords
- Глобальный поиск по публичному Telegram
- Выгрузка в Google Sheets + Excel
- Telegram-бот для управления настройками
- Синхронизация keywords и чатов с листами **Keywords** и **Чаты** в Google Таблице

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config.example.yaml config.yaml
# заполнить .env
python main.py bot
```

## Railway

1. Создайте проект на [Railway](https://railway.app/) из GitHub-репозитория
2. Добавьте переменные окружения:

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_API_ID` | API ID с my.telegram.org |
| `TELEGRAM_API_HASH` | API Hash |
| `TELEGRAM_SESSION_STRING` | Строка сессии (`python scripts/export_session.py`) |
| `TELEGRAM_BOT_TOKEN` | Токен бота |
| `BOT_ADMIN_IDS` | Ваш Telegram user id |
| `GOOGLE_SPREADSHEET_ID` | ID Google Таблицы |
| `GOOGLE_CREDENTIALS_JSON` | Содержимое credentials.json одной строкой |

3. Start command: `python main.py bot`

Настройки keywords и чатов на Railway берутся из Google Таблицы (листы **Keywords**, **Чаты**).

## Команды

```bash
python main.py bot              # бот + автопроверка
python main.py monitor scan     # разовый мониторинг
python main.py global           # глобальный поиск
python scripts/export_session.py  # экспорт сессии для облака
```

## Структура Google Таблицы

| Лист | Назначение |
|------|------------|
| Keywords | Ключевые слова (синхронизация с ботом) |
| Чаты | Чаты/каналы (синхронизация с ботом) |
| Мониторинг чатов | Найденные сообщения из ваших чатов |
| Глобальный поиск | Найденные сообщения из публичного Telegram |
