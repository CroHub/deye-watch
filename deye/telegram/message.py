"""Вхідні повідомлення бота."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Message:
    chat_id: str
    text: str
    sender: str  # @username або ім'я з профілю Telegram — для журналу
    callback_id: str = ""  # натискання inline-кнопки: її data приходить як text
    message_id: int = 0  # повідомлення з кнопкою — щоб замінити його результатом

    @property
    def is_button(self) -> bool:
        return bool(self.callback_id)


def parse_update(update: dict[str, Any]) -> Message | None:
    """Текстове повідомлення або натискання кнопки; решту (стікери, фото, ...) пропускаємо."""
    if query := update.get("callback_query"):
        msg = query.get("message") or {}
        text = query.get("data", "")
        extra: dict[str, Any] = {"callback_id": query["id"], "message_id": msg.get("message_id", 0)}
        author = query.get("from", {})
    else:
        msg = update.get("message") or {}
        text = msg.get("text")
        extra = {}
        author = msg.get("from", {})
    if text is None or "chat" not in msg:
        return None
    sender = f"@{author['username']}" if author.get("username") else author.get("first_name", "?")
    return Message(str(msg["chat"]["id"]), text.strip(), sender, **extra)
