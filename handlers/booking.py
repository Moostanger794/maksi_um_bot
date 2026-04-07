from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config
from database import Database
from keyboards.inline import build_calendar_kb, confirm_booking_kb, main_menu_kb, time_slots_kb
from scheduler.reminders import ReminderService
from states.booking import BookingFSM

router = Router()


def _month_bounds() -> tuple[date, date]:
    today = date.today()
    return today, today + timedelta(days=30)


async def _show_calendar(callback: CallbackQuery, db: Database, month: int | None = None, year: int | None = None) -> None:
    min_d, max_d = _month_bounds()
    if month is None or year is None:
        month = min_d.month
        year = min_d.year
    available = set(db.get_available_dates(min_d.isoformat(), max_d.isoformat()))
    await callback.message.edit_text(
        "Выберите дату занятия:",
        reply_markup=build_calendar_kb(
            available_dates=available,
            month=month,
            year=year,
            min_date=min_d,
            max_date=max_d,
            prefix="booking",
        ),
    )


@router.callback_query(F.data == "booking:start")
async def booking_start(callback: CallbackQuery, db: Database) -> None:
    active = db.get_user_active_booking(callback.from_user.id)
    if active is not None:
        await callback.message.answer(
            "У вас уже есть активная запись. Сначала отмените ее, чтобы выбрать другой слот."
        )
        await callback.answer()
        return
    await _show_calendar(callback, db)
    await callback.answer()


@router.callback_query(F.data.startswith("booking:month:"))
async def switch_month(callback: CallbackQuery, db: Database) -> None:
    _, _, _, year, month = callback.data.split(":")
    await _show_calendar(callback, db, int(month), int(year))
    await callback.answer()


@router.callback_query(F.data.startswith("booking:date:"))
async def choose_date(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    date_iso = callback.data.split(":")[2]
    times = db.get_available_times(date_iso)
    if not times:
        await callback.answer("На выбранную дату слотов нет.", show_alert=True)
        return
    await state.update_data(slot_date=date_iso)
    await callback.message.edit_text(
        f"Дата: {date_iso}\nВыберите время:",
        reply_markup=time_slots_kb(date_iso, times),
    )
    await callback.answer()


@router.callback_query(F.data == "booking:back_calendar")
async def back_to_calendar(callback: CallbackQuery, db: Database) -> None:
    await _show_calendar(callback, db)
    await callback.answer()


@router.callback_query(F.data.startswith("booking:time:"))
async def choose_time(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, slot_date, slot_time = callback.data.split(":", 3)
    await state.update_data(slot_date=slot_date, slot_time=slot_time)
    await state.set_state(BookingFSM.waiting_parent_and_child)
    await callback.message.edit_text(
        f"Вы выбрали {slot_date} в {slot_time}.\n"
        "Отправьте имя родителя и имя ребенка одним сообщением.\n"
        "Пример: Иванова Анна, Петр",
        reply_markup=confirm_booking_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "booking:abort")
async def abort_booking(callback: CallbackQuery, state: FSMContext, config: Config) -> None:
    await state.clear()
    await callback.message.edit_text("Запись отменена.", reply_markup=main_menu_kb(callback.from_user.id == config.admin_id))
    await callback.answer()


@router.callback_query(F.data == "booking:confirm")
async def booking_confirm_hint(callback: CallbackQuery) -> None:
    await callback.answer("Отправьте имя родителя и ребенка сообщением.")


@router.message(BookingFSM.waiting_parent_and_child)
async def input_names(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if "," not in raw:
        await message.answer("Введите данные в формате: Имя родителя, Имя ребенка")
        return
    parent_name, child_name = [p.strip() for p in raw.split(",", 1)]
    if not parent_name or not child_name:
        await message.answer("Оба имени должны быть заполнены.")
        return
    await state.update_data(parent_name=parent_name, child_name=child_name)
    await state.set_state(BookingFSM.waiting_phone)
    await message.answer("Введите номер телефона:")


@router.message(BookingFSM.waiting_phone)
async def input_phone(
    message: Message,
    state: FSMContext,
    db: Database,
    reminders: ReminderService,
    config: Config,
) -> None:
    phone = (message.text or "").strip()
    if len(phone) < 6:
        await message.answer("Введите корректный номер телефона.")
        return

    data = await state.get_data()
    booking_id = db.create_booking(
        user_id=message.from_user.id,
        parent_name=data["parent_name"],
        child_name=data["child_name"],
        phone=phone,
        slot_date=data["slot_date"],
        slot_time=data["slot_time"],
    )
    if booking_id is None:
        await message.answer("Не удалось сохранить запись: слот уже занят или у вас уже есть активная запись.")
        await state.clear()
        return

    db.set_reminder(booking_id, None, None)
    reminders.schedule_for_booking(booking_id)

    booking = db.get_booking_by_id(booking_id)
    text = (
        "✅ Запись подтверждена!\n"
        f"Дата: {booking['slot_date']}\n"
        f"Время: {booking['slot_time']}\n"
        f"Родитель: {booking['parent_name']}\n"
        f"Ребенок: {booking['child_name']}\n"
        f"Телефон: {booking['phone']}"
    )
    await message.answer(text, reply_markup=main_menu_kb(message.from_user.id == config.admin_id))

    notify = (
        "📌 Новая запись в MaksiUm\n"
        f"Дата: {booking['slot_date']} {booking['slot_time']}\n"
        f"Родитель: {booking['parent_name']}\n"
        f"Ребенок: {booking['child_name']}\n"
        f"Телефон: {booking['phone']}\n"
        f"User ID: {booking['user_id']}\n"
        f"Booking ID: {booking['id']}"
    )
    await message.bot.send_message(config.admin_id, notify)
    if config.channel_id != 0:
        try:
            await message.bot.send_message(config.channel_id, notify)
        except Exception:
            # If bot is not in channel or has no rights, do not break booking flow.
            pass
    await state.clear()


@router.callback_query(F.data == "booking:cancel_mine")
async def cancel_my_booking(
    callback: CallbackQuery,
    db: Database,
    reminders: ReminderService,
) -> None:
    row = db.cancel_user_booking(callback.from_user.id)
    if row is None:
        await callback.message.answer("У вас нет активной записи.")
        await callback.answer()
        return
    reminders.remove_for_booking(int(row["id"]))
    await callback.message.answer(
        f"Ваша запись на {row['slot_date']} {row['slot_time']} отменена. Слот снова доступен."
    )
    await callback.answer()
