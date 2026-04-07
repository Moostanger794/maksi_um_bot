from calendar import monthrange
from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗓 Записаться на занятие", callback_data="booking:start")
    kb.button(text="❌ Отменить мою запись", callback_data="booking:cancel_mine")
    kb.button(text="🏫 О центре", callback_data="info:center")
    kb.button(text="📚 Направления и цены", callback_data="info:prices")
    kb.button(text="📸 Фотогалерея", callback_data="info:gallery")
    if is_admin:
        kb.button(text="⚙️ Админ-панель", callback_data="admin:panel")
    kb.adjust(1)
    return kb.as_markup()


def check_subscription_kb(channel_link: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="Подписаться", url=channel_link))
    kb.button(text="Проверить подписку", callback_data="sub:check")
    kb.adjust(1)
    return kb.as_markup()


def build_calendar_kb(
    available_dates: set[str],
    month: int,
    year: int,
    min_date: date,
    max_date: date,
    prefix: str,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    month_title = date(year, month, 1).strftime("%B %Y").capitalize()
    kb.button(text=month_title, callback_data="noop")

    for wd in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
        kb.button(text=wd, callback_data="noop")

    first_weekday, days_count = monthrange(year, month)
    first_weekday = (first_weekday + 1) % 7
    for _ in range(first_weekday):
        kb.button(text=" ", callback_data="noop")

    for day in range(1, days_count + 1):
        current = date(year, month, day)
        current_iso = current.isoformat()
        if current < min_date or current > max_date:
            kb.button(text="·", callback_data="noop")
        elif current_iso in available_dates:
            kb.button(text=str(day), callback_data=f"{prefix}:date:{current_iso}")
        else:
            kb.button(text=f"{day}✖", callback_data="noop")

    prev_month_date = (date(year, month, 1) - timedelta(days=1)).replace(day=1)
    next_month_date = (date(year, month, 28) + timedelta(days=4)).replace(day=1)

    if prev_month_date >= min_date.replace(day=1):
        kb.button(
            text="⬅️",
            callback_data=f"{prefix}:month:{prev_month_date.year}:{prev_month_date.month}",
        )
    else:
        kb.button(text=" ", callback_data="noop")

    kb.button(text="🔙 Меню", callback_data="menu:main")

    if next_month_date <= max_date.replace(day=1):
        kb.button(
            text="➡️",
            callback_data=f"{prefix}:month:{next_month_date.year}:{next_month_date.month}",
        )
    else:
        kb.button(text=" ", callback_data="noop")

    kb.adjust(1, 7, 7, 7, 7, 7, 7, 3)
    return kb.as_markup()


def time_slots_kb(date_iso: str, times: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in times:
        kb.button(text=t, callback_data=f"booking:time:{date_iso}:{t}")
    kb.button(text="🔙 К календарю", callback_data="booking:back_calendar")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def confirm_booking_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data="booking:confirm")
    kb.button(text="❌ Отмена", callback_data="booking:abort")
    kb.adjust(2)
    return kb.as_markup()


def gallery_kb(url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="Посмотреть наш центр", url=url))
    kb.button(text="🔙 Меню", callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()


def admin_panel_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить слот", callback_data="admin:add_slot")
    kb.button(text="➖ Удалить слот", callback_data="admin:remove_slot")
    kb.button(text="🚫 Закрыть день", callback_data="admin:close_day")
    kb.button(text="✅ Открыть день", callback_data="admin:open_day")
    kb.button(text="📅 Список записей по дате", callback_data="admin:list_by_date")
    kb.button(text="❌ Отменить запись клиента", callback_data="admin:cancel_client")
    kb.button(text="🔙 Меню", callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()
