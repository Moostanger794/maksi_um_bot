from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from config import Config
from keyboards.inline import check_subscription_kb


class SubscriptionMiddleware(BaseMiddleware):
    def __init__(self, config: Config) -> None:
        self.config = config

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery):
            if self.config.channel_id == 0:
                return await handler(event, data)

            callback_data = event.data or ""
            protected_actions = {
                "booking:start",
                "booking:back_calendar",
            }
            if callback_data.startswith("booking:month:") or callback_data.startswith("booking:date:") or callback_data.startswith("booking:time:") or callback_data in protected_actions:
                bot = data["bot"]
                member = await bot.get_chat_member(self.config.channel_id, event.from_user.id)
                if member.status not in {"member", "administrator", "creator"}:
                    await event.message.answer(
                        "Для записи нужно подписаться на канал центра.",
                        reply_markup=check_subscription_kb(self.config.channel_link),
                    )
                    await event.answer()
                    return None

        return await handler(event, data)
