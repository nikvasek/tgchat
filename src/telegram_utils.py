from __future__ import annotations

from telethon.tl.types import Channel, Chat, User


def entity_title(entity) -> str:
    if hasattr(entity, "title") and entity.title:
        return entity.title
    if isinstance(entity, User):
        parts = [entity.first_name or "", entity.last_name or ""]
        return " ".join(p for p in parts if p).strip() or "Unknown"
    return "Unknown"


def entity_username(entity) -> str:
    username = getattr(entity, "username", None)
    return f"@{username}" if username else ""


def message_link(entity, message_id: int) -> str:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"

    entity_id = getattr(entity, "id", None)
    if entity_id is None:
        return ""

    if isinstance(entity, Channel):
        internal_id = abs(entity_id) - 10**12 if entity_id < 0 else entity_id
        return f"https://t.me/c/{internal_id}/{message_id}"

    return ""


def author_name(sender) -> str:
    if sender is None:
        return ""
    if isinstance(sender, User):
        parts = [sender.first_name or "", sender.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        if sender.username:
            return f"{name} (@{sender.username})" if name else f"@{sender.username}"
        return name
    if hasattr(sender, "title"):
        return sender.title or ""
    return ""
