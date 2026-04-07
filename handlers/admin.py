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
_pending_slot_selection: dict[tuple[int, str], set[str]] = {}
_pending_remove_selection: dict[tuple[int, str], set[str]] = {}


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


def _half_hour_times() -> list[str]:
    times: list[str] = []
    for hour in range(8, 21):
        times.append(f"{hour:02d}:00")
        if hour != 20:
            times.append(f"{hour:02d}:30")
    return times


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


def _add_multi_slots_kb(user_id: int, date_iso: str) -> object:
    selected = _pending_slot_selection.get((user_id, date_iso), set())
    kb = InlineKeyboardBuilder()
    for t in _half_hour_times():
        encoded = t.replace(":", "")
        mark = "✅ " if t in selected else ""
        kb.button(text=f"{mark}{t}", callback_data=f"admadd:tg:{date_iso}:{encoded}")

    kb.button(text="Выбрать все", callback_data=f"admadd:all:{date_iso}")
    kb.button(text="Очистить", callback_data=f"admadd:clr:{date_iso}")
    kb.button(text="✅ Сохранить выбранные", callback_data=f"admadd:sv:{date_iso}")
    kb.button(text="🔙 Админ", callback_data="admin:panel")
    kb.adjust(3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 2, 1, 1)
    return kb.as_markup()


def _remove_multi_slots_kb(user_id: int, date_iso: str, existing_times: list[str]) -> object:
    selected = _pending_remove_selection.get((user_id, date_iso), set())
    kb = InlineKeyboardBuilder()
    for t in existing_times:
        encoded = t.replace(":", "")
        mark = "✅ " if t in selected else ""
        kb.button(text=f"{mark}{t}", callback_data=f"admrm:tg:{date_iso}:{encoded}")

    kb.button(text="Выбрать все", callback_data=f"admrm:all:{date_iso}")
    kb.button(text="Очистить", callback_data=f"admrm:clr:{date_iso}")
    kb.button(text="🗑 Удалить выбранные", callback_data=f"admrm:sv:{date_iso}")
    kb.button(text="🔙 Админ", callback_data="admin:panel")
    kb.adjust(3, 3, 3, 3, 3, 3, 3, 3, 2, 1, 1)
    return kb.as_markup()


@router.callback_query(F.data.startswith("adminpick:") & F.data.contains(":date:"))
async def admin_pick_date(
    callback: CallbackQuery,
    db: Database,
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
        _pending_slot_selection[(callback.from_user.id, date_iso)] = set()
        await callback.message.edit_text(
            f"Добавление слотов на {date_iso}.\nВыберите одно или несколько времен (шаг 30 минут):",
            reply_markup=_add_multi_slots_kb(callback.from_user.id, date_iso),
        )
    elif action == "remove_slot":
        times = db.get_slots_for_date(date_iso)
        if not times:
            await callback.message.edit_text("На эту дату слотов нет.", reply_markup=admin_panel_kb())
        else:
            _pending_remove_selection[(callback.from_user.id, date_iso)] = set()
            await callback.message.edit_text(
                f"Удаление слотов на {date_iso}.\nВыберите одно или несколько времен:",
                reply_markup=_remove_multi_slots_kb(callback.from_user.id, date_iso, times),
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


@router.callback_query(F.data.startswith("admrm:"))
async def admin_remove_multi_slots(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    action = parts[1]
    date_iso = parts[2]
    key = (callback.from_user.id, date_iso)
    existing = db.get_slots_for_date(date_iso)
    selected = _pending_remove_selection.setdefault(key, set())

    if action == "tg":
        hhmm = parts[3]
        time_str = f"{hhmm[:2]}:{hhmm[2:]}"
        if time_str in selected:
            selected.remove(time_str)
        else:
            selected.add(time_str)
        await callback.message.edit_text(
            f"Удаление слотов на {date_iso}.\nВыбрано: {len(selected)}",
            reply_markup=_remove_multi_slots_kb(callback.from_user.id, date_iso, existing),
        )
        await callback.answer()
        return

    if action == "all":
        _pending_remove_selection[key] = set(existing)
        await callback.message.edit_text(
            f"Удаление слотов на {date_iso}.\nВыбрано: {len(_pending_remove_selection[key])}",
            reply_markup=_remove_multi_slots_kb(callback.from_user.id, date_iso, existing),
        )
        await callback.answer("Выбраны все слоты")
        return

    if action == "clr":
        _pending_remove_selection[key] = set()
        await callback.message.edit_text(
            f"Удаление слотов на {date_iso}.\nВыбрано: 0",
            reply_markup=_remove_multi_slots_kb(callback.from_user.id, date_iso, existing),
        )
        await callback.answer("Выбор очищен")
        return

    if action == "sv":
        if not selected:
            await callback.answer("Не выбрано ни одного времени.", show_alert=True)
            return

        removed = 0
        for t in sorted(selected):
            before = set(db.get_slots_for_date(date_iso))
            db.remove_slot(date_iso, t)
            after = set(db.get_slots_for_date(date_iso))
            if t in before and t not in after:
                removed += 1

        total = len(selected)
        _pending_remove_selection.pop(key, None)
        await callback.message.edit_text(
            f"Удаление завершено.\nУдалено: {removed}\nНе удалено (занятые/отсутствуют): {total - removed}",
            reply_markup=admin_panel_kb(),
        )
        await callback.answer("Готово")
        return

    await callback.answer()


@router.callback_query(F.data.startswith("admadd:"))
async def admin_add_multi_slots(callback: CallbackQuery, db: Database, config: Config) -> None:
    if not _is_admin(callback.from_user.id, config):
        await callback.answer("Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    action = parts[1]
    date_iso = parts[2]
    key = (callback.from_user.id, date_iso)
    selected = _pending_slot_selection.setdefault(key, set())

    if action == "tg":
        hhmm = parts[3]
        time_str = f"{hhmm[:2]}:{hhmm[2:]}"
        if time_str in selected:
            selected.remove(time_str)
        else:
            selected.add(time_str)
        await callback.message.edit_text(
            f"Добавление слотов на {date_iso}.\nВыбрано: {len(selected)}",
            reply_markup=_add_multi_slots_kb(callback.from_user.id, date_iso),
        )
        await callback.answer()
        return

    if action == "all":
        _pending_slot_selection[key] = set(_half_hour_times())
        await callback.message.edit_text(
            f"Добавление слотов на {date_iso}.\nВыбрано: {len(_pending_slot_selection[key])}",
            reply_markup=_add_multi_slots_kb(callback.from_user.id, date_iso),
        )
        await callback.answer("Выбраны все слоты")
        return

    if action == "clr":
        _pending_slot_selection[key] = set()
        await callback.message.edit_text(
            f"Добавление слотов на {date_iso}.\nВыбрано: 0",
            reply_markup=_add_multi_slots_kb(callback.from_user.id, date_iso),
        )
        await callback.answer("Выбор очищен")
        return

    if action == "sv":
        if not selected:
            await callback.answer("Не выбрано ни одного времени.", show_alert=True)
            return
        for t in sorted(selected):
            db.add_slot(date_iso, t)
        added_count = len(selected)
        _pending_slot_selection.pop(key, None)
        await callback.message.edit_text(
            f"Добавлено слотов на {date_iso}: {added_count}",
            reply_markup=admin_panel_kb(),
        )
        await callback.answer("Слоты сохранены")
        return

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
