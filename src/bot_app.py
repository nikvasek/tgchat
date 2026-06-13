from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile, KeyboardButton, Message, ReplyKeyboardMarkup, User
from telethon import TelegramClient

from .config import EnvConfig
from .config_store import ConfigStore
from .scheduler import MonitorScheduler

logger = logging.getLogger(__name__)

BTN_CHATS = "📋 Чаты"
BTN_KEYWORDS = "🔑 Keywords"
BTN_INTERVAL = "⏱ Интервал"
BTN_GOOGLE = "🔗 Google"
BTN_WEBHOOK = "🌐 Webhook"
BTN_EXCEL = "📊 Excel"
BTN_STATUS = "📈 Статус"
BTN_SYNC = "🔄 Синхронизация"
BTN_SCAN_START = "▶️ Запустить сканирование"
BTN_SCAN_STOP = "⏹ Остановить сканирование"
BTN_PIPE_START = "▶️ Запустить ТРУБУ"
BTN_PIPE_STOP = "⏹ Остановить ТРУБУ"
BTN_BACK = "« Главное меню"

BTN_CHAT_ADD = "➕ Добавить чат"
BTN_CHAT_DEL = "➖ Удалить чат"
BTN_CHAT_LIST = "📋 Список чатов"

BTN_KW_ADD = "➕ Добавить keyword"
BTN_KW_DEL = "➖ Удалить keyword"
BTN_KW_LIST = "📋 Список keywords"


class Form(StatesGroup):
    add_chat = State()
    del_chat = State()
    add_keyword = State()
    del_keyword = State()
    set_interval = State()
    set_google = State()
    set_webhook = State()


def main_menu_kb(scanning_enabled: bool, pipe_enabled: bool) -> ReplyKeyboardMarkup:
    scan_button = BTN_SCAN_STOP if scanning_enabled else BTN_SCAN_START
    pipe_button = BTN_PIPE_STOP if pipe_enabled else BTN_PIPE_START
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CHATS), KeyboardButton(text=BTN_KEYWORDS)],
            [KeyboardButton(text=BTN_INTERVAL), KeyboardButton(text=BTN_GOOGLE)],
            [KeyboardButton(text=BTN_WEBHOOK), KeyboardButton(text=BTN_EXCEL)],
            [KeyboardButton(text=BTN_STATUS), KeyboardButton(text=BTN_SYNC)],
            [KeyboardButton(text=scan_button), KeyboardButton(text=pipe_button)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def chats_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CHAT_ADD), KeyboardButton(text=BTN_CHAT_DEL)],
            [KeyboardButton(text=BTN_CHAT_LIST)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def keywords_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_KW_ADD), KeyboardButton(text=BTN_KW_DEL)],
            [KeyboardButton(text=BTN_KW_LIST)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _user_label(user: User | None) -> str:
    if user is None:
        return "Неизвестный пользователь"
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(part for part in parts if part).strip() or "Без имени"
    username = f" (@{user.username})" if user.username else ""
    return f"{name}{username} [id: {user.id}]"


class BotApp:
    def __init__(
        self,
        env: EnvConfig,
        store: ConfigStore,
        telethon_client: TelegramClient,
        scheduler: MonitorScheduler,
        bot: Bot | None = None,
    ):
        if not env.bot_token:
            raise ValueError("Укажите TELEGRAM_BOT_TOKEN в .env")

        self.env = env
        self.store = store
        self.telethon_client = telethon_client
        self.scheduler = scheduler
        self.bot = bot or Bot(token=env.bot_token)
        self.dp = Dispatcher(storage=MemoryStorage())
        self._register_handlers()

    async def _notify_admins(self, text: str) -> None:
        if not self.env.admin_ids:
            return
        for admin_id in self.env.admin_ids:
            try:
                await self.bot.send_message(admin_id, text)
            except Exception as error:
                logger.warning("Не удалось уведомить админа %s: %s", admin_id, error)

    async def _notify_user_joined(self, user: User | None) -> None:
        if not self.env.admin_ids:
            return
        await self._notify_admins(f"👤 Новый пользователь в боте:\n{_user_label(user)}")

    async def _main_menu_markup(self) -> ReplyKeyboardMarkup:
        scanning = await self.store.is_scanning_enabled()
        pipe_enabled = await self.store.is_pipe_enabled()
        return main_menu_kb(scanning, pipe_enabled)

    async def _show_main_menu(self, message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "Панель управления парсером Telegram.\nВыберите действие:",
            reply_markup=await self._main_menu_markup(),
        )

    def _register_handlers(self) -> None:
        @self.dp.message(Command("start"))
        async def cmd_start(message: Message, state: FSMContext):
            await state.clear()
            await self._notify_user_joined(message.from_user)
            await message.answer(
                "Панель управления парсером Telegram.\n\n"
                "Keywords и чаты синхронизируются с листами\n"
                "<b>Keywords</b> и <b>Чаты</b> в Google Таблице.\n\n"
                "<b>ТРУБА</b> — все новые сообщения из списка чатов\n"
                "сохраняются в PostgreSQL и отправляются на webhook.\n\n"
                "Используйте кнопки под полем ввода:",
                reply_markup=await self._main_menu_markup(),
                parse_mode="HTML",
            )

        @self.dp.message(F.text == BTN_BACK)
        async def back_to_main(message: Message, state: FSMContext):
            await self._show_main_menu(message, state)

        @self.dp.message(F.text == BTN_CHATS, StateFilter(None))
        async def menu_chats(message: Message, state: FSMContext):
            await state.clear()
            await message.answer("Управление чатами:", reply_markup=chats_menu_kb())

        @self.dp.message(F.text == BTN_KEYWORDS, StateFilter(None))
        async def menu_keywords(message: Message, state: FSMContext):
            await state.clear()
            await message.answer("Управление ключевыми словами:", reply_markup=keywords_menu_kb())

        @self.dp.message(F.text == BTN_CHAT_LIST)
        async def chats_list(message: Message):
            await self.store.sync_from_google()
            data = await self.store.get_raw()
            chats = data.get("chats", [])
            if not chats:
                text = "Список чатов пуст."
            else:
                lines = [f"{i}. {chat}" for i, chat in enumerate(chats, 1)]
                text = "Чаты:\n" + "\n".join(lines)
            await message.answer(text, reply_markup=chats_menu_kb())

        @self.dp.message(F.text == BTN_KW_LIST)
        async def kw_list(message: Message):
            await self.store.sync_from_google()
            data = await self.store.get_raw()
            keywords = data.get("keywords", [])
            if not keywords:
                text = "Список keywords пуст."
            else:
                lines = [f"{i}. {kw}" for i, kw in enumerate(keywords, 1)]
                text = "Keywords:\n" + "\n".join(lines)
            await message.answer(text, reply_markup=keywords_menu_kb())

        @self.dp.message(F.text == BTN_CHAT_ADD)
        async def chats_add(message: Message, state: FSMContext):
            await state.set_state(Form.add_chat)
            await message.answer(
                "Отправьте @username, ссылку t.me/... или ID чата:",
                reply_markup=chats_menu_kb(),
            )

        @self.dp.message(F.text == BTN_CHAT_DEL)
        async def chats_del(message: Message, state: FSMContext):
            data = await self.store.get_raw()
            chats = data.get("chats", [])
            hint = "\n".join(f"{i}. {c}" for i, c in enumerate(chats, 1)) if chats else "— пусто"
            await state.set_state(Form.del_chat)
            await message.answer(
                f"Отправьте номер или @username для удаления:\n\n{hint}",
                reply_markup=chats_menu_kb(),
            )

        @self.dp.message(F.text == BTN_KW_ADD)
        async def kw_add(message: Message, state: FSMContext):
            await state.set_state(Form.add_keyword)
            await message.answer("Отправьте ключевое слово:", reply_markup=keywords_menu_kb())

        @self.dp.message(F.text == BTN_KW_DEL)
        async def kw_del(message: Message, state: FSMContext):
            data = await self.store.get_raw()
            keywords = data.get("keywords", [])
            hint = "\n".join(f"{i}. {k}" for i, k in enumerate(keywords, 1)) if keywords else "— пусто"
            await state.set_state(Form.del_keyword)
            await message.answer(
                f"Отправьте номер или слово для удаления:\n\n{hint}",
                reply_markup=keywords_menu_kb(),
            )

        @self.dp.message(F.text == BTN_INTERVAL, StateFilter(None))
        async def menu_interval(message: Message, state: FSMContext):
            data = await self.store.get_raw()
            minutes = data.get("monitor", {}).get("poll_interval", 300) // 60
            await state.set_state(Form.set_interval)
            await message.answer(
                f"Текущий интервал: {minutes} мин.\n"
                "Отправьте новый интервал в минутах (например, 5):",
                reply_markup=await self._main_menu_markup(),
            )

        @self.dp.message(F.text == BTN_GOOGLE, StateFilter(None))
        async def menu_google(message: Message, state: FSMContext):
            data = await self.store.get_raw()
            url = data.get("google_sheets_url", "")
            await state.set_state(Form.set_google)
            await message.answer(
                f"Текущая ссылка:\n{url or '— не задана'}\n\n"
                "Отправьте новую ссылку на Google Таблицу\n"
                "(или «-» чтобы удалить):",
                reply_markup=await self._main_menu_markup(),
            )

        @self.dp.message(F.text == BTN_WEBHOOK, StateFilter(None))
        async def menu_webhook(message: Message, state: FSMContext):
            data = await self.store.get_raw()
            url = data.get("webhook_url", "")
            await state.set_state(Form.set_webhook)
            await message.answer(
                f"Текущий webhook:\n{url or '— не задан'}\n\n"
                "Отправьте URL Google Apps Script (или другой webhook)\n"
                "(или «-» чтобы удалить):",
                reply_markup=await self._main_menu_markup(),
            )

        @self.dp.message(F.text == BTN_SYNC, StateFilter(None))
        async def action_sync(message: Message):
            changed, pull_message = await self.store.sync_from_google()
            ok, push_message = await self.store.push_to_google()
            text = "Синхронизация завершена.\n"
            text += f"Из Google: {pull_message}\n"
            text += f"В Google: {push_message if ok else push_message}"
            if changed:
                text += "\n\nНастройки обновлены из таблицы."
            await message.answer(text, reply_markup=await self._main_menu_markup())

        @self.dp.message(F.text == BTN_STATUS, StateFilter(None))
        async def action_status(message: Message):
            text = await self.store.format_status()
            await message.answer(text, reply_markup=await self._main_menu_markup(), parse_mode="HTML")

        @self.dp.message(F.text == BTN_EXCEL, StateFilter(None))
        async def action_export(message: Message):
            path = Path(self.env.excel_output_file)
            if not path.exists():
                await message.answer("Файл Excel ещё не создан.", reply_markup=await self._main_menu_markup())
                return
            await message.answer_document(FSInputFile(path))
            data = await self.store.get_raw()
            google_url = data.get("google_sheets_url", "")
            if google_url:
                await message.answer(
                    f"Google Таблица:\n{google_url}",
                    reply_markup=await self._main_menu_markup(),
                )

        @self.dp.message(F.text == BTN_SCAN_START, StateFilter(None))
        async def action_scan_start(message: Message):
            _, result = await self.store.set_scanning_enabled(True)
            await message.answer(result, reply_markup=main_menu_kb(True, await self.store.is_pipe_enabled()))

        @self.dp.message(F.text == BTN_SCAN_STOP, StateFilter(None))
        async def action_scan_stop(message: Message):
            _, result = await self.store.set_scanning_enabled(False)
            await message.answer(result, reply_markup=main_menu_kb(False, await self.store.is_pipe_enabled()))

        @self.dp.message(F.text == BTN_PIPE_START, StateFilter(None))
        async def action_pipe_start(message: Message):
            _, result = await self.store.set_pipe_enabled(True)
            await message.answer(result, reply_markup=main_menu_kb(await self.store.is_scanning_enabled(), True))

        @self.dp.message(F.text == BTN_PIPE_STOP, StateFilter(None))
        async def action_pipe_stop(message: Message):
            _, result = await self.store.set_pipe_enabled(False)
            await message.answer(result, reply_markup=main_menu_kb(await self.store.is_scanning_enabled(), False))

        @self.dp.message(Form.add_chat)
        async def form_add_chat(message: Message, state: FSMContext):
            if message.text in {BTN_BACK, BTN_CHATS, BTN_CHAT_LIST, BTN_CHAT_ADD, BTN_CHAT_DEL}:
                await state.clear()
                if message.text == BTN_BACK:
                    await self._show_main_menu(message, state)
                return
            ok, result = await self.store.add_chat(message.text or "")
            await state.clear()
            await message.answer(
                result,
                reply_markup=await self._main_menu_markup() if ok else chats_menu_kb(),
            )

        @self.dp.message(Form.del_chat)
        async def form_del_chat(message: Message, state: FSMContext):
            if message.text in {BTN_BACK, BTN_CHATS, BTN_CHAT_LIST, BTN_CHAT_ADD, BTN_CHAT_DEL}:
                await state.clear()
                if message.text == BTN_BACK:
                    await self._show_main_menu(message, state)
                return
            ok, result = await self.store.remove_chat(message.text or "")
            await state.clear()
            await message.answer(
                result,
                reply_markup=await self._main_menu_markup() if ok else chats_menu_kb(),
            )

        @self.dp.message(Form.add_keyword)
        async def form_add_keyword(message: Message, state: FSMContext):
            if message.text in {BTN_BACK, BTN_KEYWORDS, BTN_KW_LIST, BTN_KW_ADD, BTN_KW_DEL}:
                await state.clear()
                if message.text == BTN_BACK:
                    await self._show_main_menu(message, state)
                return
            ok, result = await self.store.add_keyword(message.text or "")
            await state.clear()
            await message.answer(
                result,
                reply_markup=await self._main_menu_markup() if ok else keywords_menu_kb(),
            )

        @self.dp.message(Form.del_keyword)
        async def form_del_keyword(message: Message, state: FSMContext):
            if message.text in {BTN_BACK, BTN_KEYWORDS, BTN_KW_LIST, BTN_KW_ADD, BTN_KW_DEL}:
                await state.clear()
                if message.text == BTN_BACK:
                    await self._show_main_menu(message, state)
                return
            ok, result = await self.store.remove_keyword(message.text or "")
            await state.clear()
            await message.answer(
                result,
                reply_markup=await self._main_menu_markup() if ok else keywords_menu_kb(),
            )

        @self.dp.message(Form.set_interval)
        async def form_set_interval(message: Message, state: FSMContext):
            if message.text == BTN_BACK:
                await self._show_main_menu(message, state)
                return
            text = (message.text or "").strip()
            if not text.isdigit():
                await message.answer("Введите число минут, например: 5")
                return
            minutes = int(text)
            if minutes < 1:
                await message.answer("Минимальный интервал — 1 минута")
                return
            _, result = await self.store.set_interval(minutes)
            await state.clear()
            await message.answer(result, reply_markup=await self._main_menu_markup())

        @self.dp.message(Form.set_google)
        async def form_set_google(message: Message, state: FSMContext):
            if message.text == BTN_BACK:
                await self._show_main_menu(message, state)
                return
            url = (message.text or "").strip()
            if url == "-":
                url = ""
            _, result = await self.store.set_google_url(url)
            await state.clear()
            await message.answer(result, reply_markup=await self._main_menu_markup())

        @self.dp.message(Form.set_webhook)
        async def form_set_webhook(message: Message, state: FSMContext):
            if message.text == BTN_BACK:
                await self._show_main_menu(message, state)
                return
            url = (message.text or "").strip()
            if url == "-":
                url = ""
            _, result = await self.store.set_webhook_url(url)
            await state.clear()
            await message.answer(result, reply_markup=await self._main_menu_markup())

    async def run(self) -> None:
        await self.dp.start_polling(self.bot)
