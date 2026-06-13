from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)
from telethon import TelegramClient

from .config import EnvConfig
from .config_store import ConfigStore
from .scheduler import MonitorScheduler

logger = logging.getLogger(__name__)


class Form(StatesGroup):
    add_chat = State()
    del_chat = State()
    add_keyword = State()
    del_keyword = State()
    set_interval = State()
    set_google = State()


def main_menu_kb(scanning_enabled: bool) -> InlineKeyboardMarkup:
    scan_button = (
        InlineKeyboardButton(text="⏹ Остановить сканирование", callback_data="action:scan_stop")
        if scanning_enabled
        else InlineKeyboardButton(text="▶️ Запустить сканирование", callback_data="action:scan_start")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Чаты", callback_data="menu:chats"),
                InlineKeyboardButton(text="🔑 Keywords", callback_data="menu:keywords"),
            ],
            [
                InlineKeyboardButton(text="⏱ Интервал", callback_data="menu:interval"),
                InlineKeyboardButton(text="🔗 Google", callback_data="menu:google"),
            ],
            [
                InlineKeyboardButton(text="📊 Excel", callback_data="action:export"),
                InlineKeyboardButton(text="📈 Статус", callback_data="action:status"),
            ],
            [scan_button],
            [InlineKeyboardButton(text="🔄 Синхронизация Google", callback_data="action:sync")],
        ]
    )


def chats_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить чат", callback_data="chats:add")],
            [InlineKeyboardButton(text="➖ Удалить чат", callback_data="chats:del")],
            [InlineKeyboardButton(text="📋 Список", callback_data="chats:list")],
            [InlineKeyboardButton(text="« Назад", callback_data="menu:main")],
        ]
    )


def keywords_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="kw:add")],
            [InlineKeyboardButton(text="➖ Удалить", callback_data="kw:del")],
            [InlineKeyboardButton(text="📋 Список", callback_data="kw:list")],
            [InlineKeyboardButton(text="« Назад", callback_data="menu:main")],
        ]
    )


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="menu:main")]]
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

    def _register_handlers(self) -> None:
        @self.dp.message(Command("start"))
        async def cmd_start(message: Message, state: FSMContext):
            await state.clear()
            await self._notify_user_joined(message.from_user)
            scanning = await self.store.is_scanning_enabled()
            await message.answer(
                "Панель управления парсером Telegram.\n\n"
                "Keywords и чаты синхронизируются с листами\n"
                "<b>Keywords</b> и <b>Чаты</b> в Google Таблице.\n\n"
                "Выберите действие:",
                reply_markup=main_menu_kb(scanning),
                parse_mode="HTML",
            )

        @self.dp.callback_query(F.data == "menu:main")
        async def menu_main(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            scanning = await self.store.is_scanning_enabled()
            await callback.message.edit_text(
                "Панель управления парсером Telegram.\nВыберите действие:",
                reply_markup=main_menu_kb(scanning),
            )
            await callback.answer()

        @self.dp.callback_query(F.data == "menu:chats")
        async def menu_chats(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.message.edit_text("Управление чатами:", reply_markup=chats_menu_kb())
            await callback.answer()

        @self.dp.callback_query(F.data == "menu:keywords")
        async def menu_keywords(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.message.edit_text(
                "Управление ключевыми словами:",
                reply_markup=keywords_menu_kb(),
            )
            await callback.answer()

        @self.dp.callback_query(F.data == "chats:list")
        async def chats_list(callback: CallbackQuery):
            await self.store.sync_from_google()
            data = await self.store.get_raw()
            chats = data.get("chats", [])
            if not chats:
                text = "Список чатов пуст."
            else:
                lines = [f"{i}. {chat}" for i, chat in enumerate(chats, 1)]
                text = "Чаты:\n" + "\n".join(lines)
            await callback.message.edit_text(text, reply_markup=chats_menu_kb())
            await callback.answer()

        @self.dp.callback_query(F.data == "kw:list")
        async def kw_list(callback: CallbackQuery):
            await self.store.sync_from_google()
            data = await self.store.get_raw()
            keywords = data.get("keywords", [])
            if not keywords:
                text = "Список keywords пуст."
            else:
                lines = [f"{i}. {kw}" for i, kw in enumerate(keywords, 1)]
                text = "Keywords:\n" + "\n".join(lines)
            await callback.message.edit_text(text, reply_markup=keywords_menu_kb())
            await callback.answer()

        @self.dp.callback_query(F.data == "chats:add")
        async def chats_add(callback: CallbackQuery, state: FSMContext):
            await state.set_state(Form.add_chat)
            await callback.message.edit_text(
                "Отправьте @username, ссылку t.me/... или ID чата:",
                reply_markup=back_kb(),
            )
            await callback.answer()

        @self.dp.callback_query(F.data == "chats:del")
        async def chats_del(callback: CallbackQuery, state: FSMContext):
            data = await self.store.get_raw()
            chats = data.get("chats", [])
            hint = "\n".join(f"{i}. {c}" for i, c in enumerate(chats, 1)) if chats else "— пусто"
            await state.set_state(Form.del_chat)
            await callback.message.edit_text(
                f"Отправьте номер или @username для удаления:\n\n{hint}",
                reply_markup=back_kb(),
            )
            await callback.answer()

        @self.dp.callback_query(F.data == "kw:add")
        async def kw_add(callback: CallbackQuery, state: FSMContext):
            await state.set_state(Form.add_keyword)
            await callback.message.edit_text(
                "Отправьте ключевое слово:",
                reply_markup=back_kb(),
            )
            await callback.answer()

        @self.dp.callback_query(F.data == "kw:del")
        async def kw_del(callback: CallbackQuery, state: FSMContext):
            data = await self.store.get_raw()
            keywords = data.get("keywords", [])
            hint = "\n".join(f"{i}. {k}" for i, k in enumerate(keywords, 1)) if keywords else "— пусто"
            await state.set_state(Form.del_keyword)
            await callback.message.edit_text(
                f"Отправьте номер или слово для удаления:\n\n{hint}",
                reply_markup=back_kb(),
            )
            await callback.answer()

        @self.dp.callback_query(F.data == "menu:interval")
        async def menu_interval(callback: CallbackQuery, state: FSMContext):
            data = await self.store.get_raw()
            minutes = data.get("monitor", {}).get("poll_interval", 300) // 60
            await state.set_state(Form.set_interval)
            await callback.message.edit_text(
                f"Текущий интервал: {minutes} мин.\n"
                "Отправьте новый интервал в минутах (например, 5):",
                reply_markup=back_kb(),
            )
            await callback.answer()

        @self.dp.callback_query(F.data == "menu:google")
        async def menu_google(callback: CallbackQuery, state: FSMContext):
            data = await self.store.get_raw()
            url = data.get("google_sheets_url", "")
            await state.set_state(Form.set_google)
            await callback.message.edit_text(
                f"Текущая ссылка:\n{url or '— не задана'}\n\n"
                "Отправьте новую ссылку на Google Таблицу\n"
                "(или «-» чтобы удалить):",
                reply_markup=back_kb(),
            )
            await callback.answer()

        @self.dp.callback_query(F.data == "action:sync")
        async def action_sync(callback: CallbackQuery):
            await callback.answer("Синхронизация...")
            changed, pull_message = await self.store.sync_from_google()
            ok, push_message = await self.store.push_to_google()
            text = "Синхронизация завершена.\n"
            text += f"Из Google: {pull_message}\n"
            text += f"В Google: {push_message if ok else push_message}"
            if changed:
                text += "\n\nНастройки обновлены из таблицы."
            scanning = await self.store.is_scanning_enabled()
            await callback.message.answer(text, reply_markup=main_menu_kb(scanning))

        @self.dp.callback_query(F.data == "action:status")
        async def action_status(callback: CallbackQuery):
            text = await self.store.format_status()
            scanning = await self.store.is_scanning_enabled()
            await callback.message.edit_text(
                text,
                reply_markup=main_menu_kb(scanning),
                parse_mode="HTML",
            )
            await callback.answer()

        @self.dp.callback_query(F.data == "action:export")
        async def action_export(callback: CallbackQuery):
            path = Path(self.env.excel_output_file)
            if not path.exists():
                await callback.answer("Файл Excel ещё не создан", show_alert=True)
                return
            await callback.message.answer_document(FSInputFile(path))
            data = await self.store.get_raw()
            google_url = data.get("google_sheets_url", "")
            if google_url:
                await callback.message.answer(f"Google Таблица:\n{google_url}")
            await callback.answer("Файл отправлен")

        @self.dp.callback_query(F.data == "action:scan_start")
        async def action_scan_start(callback: CallbackQuery):
            ok, result = await self.store.set_scanning_enabled(True)
            await callback.answer(result, show_alert=True)
            await callback.message.edit_reply_markup(reply_markup=main_menu_kb(True))

        @self.dp.callback_query(F.data == "action:scan_stop")
        async def action_scan_stop(callback: CallbackQuery):
            ok, result = await self.store.set_scanning_enabled(False)
            await callback.answer(result, show_alert=True)
            await callback.message.edit_reply_markup(reply_markup=main_menu_kb(False))

        @self.dp.message(Form.add_chat)
        async def form_add_chat(message: Message, state: FSMContext):
            ok, result = await self.store.add_chat(message.text or "")
            await state.clear()
            scanning = await self.store.is_scanning_enabled()
            await message.answer(result, reply_markup=main_menu_kb(scanning) if ok else chats_menu_kb())

        @self.dp.message(Form.del_chat)
        async def form_del_chat(message: Message, state: FSMContext):
            ok, result = await self.store.remove_chat(message.text or "")
            await state.clear()
            scanning = await self.store.is_scanning_enabled()
            await message.answer(result, reply_markup=main_menu_kb(scanning) if ok else chats_menu_kb())

        @self.dp.message(Form.add_keyword)
        async def form_add_keyword(message: Message, state: FSMContext):
            ok, result = await self.store.add_keyword(message.text or "")
            await state.clear()
            scanning = await self.store.is_scanning_enabled()
            await message.answer(result, reply_markup=main_menu_kb(scanning) if ok else keywords_menu_kb())

        @self.dp.message(Form.del_keyword)
        async def form_del_keyword(message: Message, state: FSMContext):
            ok, result = await self.store.remove_keyword(message.text or "")
            await state.clear()
            scanning = await self.store.is_scanning_enabled()
            await message.answer(result, reply_markup=main_menu_kb(scanning) if ok else keywords_menu_kb())

        @self.dp.message(Form.set_interval)
        async def form_set_interval(message: Message, state: FSMContext):
            text = (message.text or "").strip()
            if not text.isdigit():
                await message.answer("Введите число минут, например: 5")
                return
            minutes = int(text)
            if minutes < 1:
                await message.answer("Минимальный интервал — 1 минута")
                return
            ok, result = await self.store.set_interval(minutes)
            await state.clear()
            scanning = await self.store.is_scanning_enabled()
            await message.answer(result, reply_markup=main_menu_kb(scanning))

        @self.dp.message(Form.set_google)
        async def form_set_google(message: Message, state: FSMContext):
            url = (message.text or "").strip()
            if url == "-":
                url = ""
            ok, result = await self.store.set_google_url(url)
            await state.clear()
            scanning = await self.store.is_scanning_enabled()
            await message.answer(result, reply_markup=main_menu_kb(scanning))

    async def run(self) -> None:
        await self.dp.start_polling(self.bot)
