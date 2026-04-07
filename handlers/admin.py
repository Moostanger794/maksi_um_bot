from calendar import monthrange
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import Config
from database import Database
from keyboards.inline import admin_panel_kb
from scheduler.reminders import ReminderService

router = Router()


def _is_admin(user_id: int, config: Config) -> bool:
    return user_id == config.admin_id


@router.callback_query(F.data == "admin:panel")
async def admin_panel(callback: CallbackQuery, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Админ-панель:", reply_markup=admin_panel_kb())
    await callback.answer()


def _month_window() -> tuple[date, date]:
    start = date.today()
    return start, start + timedelta(days=30)


def _admin_calendar(action: str, month: int, year: int) -> object:
    min_d, max_d = _month_window()
    kb = InlineKeyboardBuilder()
    kb.button(text=date(year, month, 1).strftime("%B %Y").capitalize(), callback_data="noop")
    for wd in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
        kb.button(text=wd, callback_data="noop")

    first_weekday, days_count = monthrange(year, month)
    first_weekday = (first_weekday + 1) % 7
    for _ in range(first_weekday):
        kb.button(text=" ", callback_data="noop")

    for d in range(1, days_count + 1):
        curr = date(year, month, d)
        curr_iso = curr.isoformat()
        if curr < min_d or curr > max_d:
            kb.button(text="·", callback_data="noop")
        else:
            kb.button(text=str(d), callback_data=f"adminpick:{action}:date:{curr_iso}")

    prev_m = (date(year, month, 1) - timedelta(days=1)).replace(day=1)
    next_m = (date(year, month, 28) + timedelta(days=4)).replace(day=1)
    if prev_m >= min_d.replace(day=1):
        kb.button(text="⬅️", callback_data=f"adminpick:{action}:month:{prev_m.year}:{prev_m.month}")
    else:
        kb.button(text=" ", callback_data="noop")
    kb.button(text="🔙 Админ", callback_data="admin:panel")
    if next_m <= max_d.replace(day=1):
        kb.button(text="➡️", callback_data=f"adminpick:{action}:month:{next_m.year}:{next_m.month}")
    else:
        kb.button(text=" ", callback_data="noop")
    kb.adjust(1, 7, 7, 7, 7, 7, 7, 3)
    return kb.as_markup()


@router.callback_query(F.data.in_({"admin:add_slot", "admin:remove_slot", "admin:close_day", "admin:open_day", "admin:list_by_date", "admin:cancel_client"}))
async def choose_date_flow(callback: CallbackQuery, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer("Нет доступа", show_alert=True)
        return
    action = callback.data.split(":")[1]
    today = date.today()
    await callback.message.edit_text(
        "Выберите дату:",
        reply_markup=_admin_calendar(action=action, month=today.month, year=today.year),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adminpick:") & F.data.contains(":month:"))
async def admin_switch_month(callback: CallbackQuery, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, action, _, year, month = callback.data.split(":")
    await callback.message.edit_text(
        "Выберите дату:",
        reply_markup=_admin_calendar(action=action, month=int(month), year=int(year)),
    )
    await callback.answer()


def _time_buttons(action: str, date_iso: str, times: list[str]) -> object:
    kb = InlineKeyboardBuilder()
    for t in times:
        kb.button(text=t, callback_data=f"adminpick:{action}:time:{date_iso}:{t}")
    kb.button(text="🔙 Админ", callback_data="admin:panel")
    kb.adjust(3, 3, 3, 3, 1)
    return kb.as_markup()


@router.callback_query(F.data.startswith("adminpick:") & F.data.contains(":date:"))
async def admin_pick_date(
    callback: CallbackQuery,
    db: Database,
    reminders: ReminderService,
    config: Config,
) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, action, _, date_iso = callback.data.split(":")

    if action == "close_day":
        db.close_day(date_iso)
        await callback.message.edit_text(f"День {date_iso} закрыт.", reply_markup=admin_panel_kb())
    elif action == "open_day":
        db.open_day(date_iso)
        await callback.message.edit_text(f"День {date_iso} открыт.", reply_markup=admin_panel_kb())
    elif action == "list_by_date":
        items = db.get_date_bookings(date_iso)
        if not items:
            await callback.message.edit_text("На эту дату записей нет.", reply_markup=admin_panel_kb())
        else:
            lines = [f"Записи на {date_iso}:"]
            for b in items:
                lines.append(f"#{b['id']} | {b['slot_time']} | {b['child_name']} ({b['parent_name']}) | {b['phone']}")
            await callback.message.edit_text("\n".join(lines), reply_markup=admin_panel_kb())
    elif action == "add_slot":
        times = [f"{h:02d}:00" for h in range(9, 21)]
        await callback.message.edit_text(
            f"Добавление слота на {date_iso}. Выберите время:",
            reply_markup=_time_buttons(action, date_iso, times),
        )
    elif action == "remove_slot":
        times = db.get_slots_for_date(date_iso)
        if not times:
            await callback.message.edit_text("На эту дату слотов нет.", reply_markup=admin_panel_kb())
        else:
            await callback.message.edit_text(
                f"Удаление слота на {date_iso}. Выберите время:",
                reply_markup=_time_buttons(action, date_iso, times),
            )
    elif action == "cancel_client":
        bookings = db.get_date_bookings(date_iso)
        kb = InlineKeyboardBuilder()
        if not bookings:
            await callback.message.edit_text("На эту дату нет активных записей.", reply_markup=admin_panel_kb())
        else:
            for b in bookings:
                kb.button(
                    text=f"#{b['id']} {b['slot_time']} {b['child_name']}",
                    callback_data=f"admin:cancel_booking:{b['id']}",
                )
            kb.button(text="🔙 Админ", callback_data="admin:panel")
            kb.adjust(1)
            await callback.message.edit_text("Выберите запись для отмены:", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("adminpick:") & F.data.contains(":time:"))
async def admin_pick_time(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer("Нет доступа", show_alert=True)
        return
    _, action, _, date_iso, time_str = callback.data.split(":", 4)
    if action == "add_slot":
        db.add_slot(date_iso, time_str)
        await callback.message.edit_text(f"Слот {date_iso} {time_str} добавлен.", reply_markup=admin_panel_kb())
    elif action == "remove_slot":
        db.remove_slot(date_iso, time_str)
        await callback.message.edit_text(
            "Удаление выполнено (если слот не был занят).",
            reply_markup=admin_panel_kb(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:cancel_booking:"))
async def admin_cancel_booking(
    callback: CallbackQuery,
    db: Database,
    reminders: ReminderService,
    config: Config,
) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer("Нет доступа", show_alert=True)
        return
    booking_id = int(callback.data.split(":")[2])
    row = db.get_booking_by_id(booking_id)
    if row is None or row["status"] != "active":
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    db.cancel_booking(booking_id)
    reminders.remove_for_booking(booking_id)
    await callback.bot.send_message(
        row["user_id"],
        f"Ваша запись на {row['slot_date']} {row['slot_time']} отменена администратором.",
    )
    await callback.message.edit_text("Запись клиента отменена.", reply_markup=admin_panel_kb())
    await callback.answer()
