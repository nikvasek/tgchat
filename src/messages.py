from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


HEADERS = [
    "Дата находки",
    "Источник",
    "Чат",
    "Username чата",
    "Ключевое слово",
    "Автор",
    "Дата сообщения",
    "Текст",
    "Ссылка",
    "ID сообщения",
]


@dataclass
class FoundMessage:
    source: str
    chat_title: str
    chat_username: str
    keyword: str
    author: str
    message_date: datetime
    text: str
    link: str
    message_id: int

    @property
    def dedup_key(self) -> str:
        return f"{self.source}:{self.chat_username or self.chat_title}:{self.message_id}"

    def to_row(self, found_at: str) -> list[str]:
        return [
            found_at,
            self.source,
            self.chat_title,
            self.chat_username,
            self.keyword,
            self.author,
            self.message_date.strftime("%Y-%m-%d %H:%M:%S"),
            self.text,
            self.link,
            str(self.message_id),
        ]
