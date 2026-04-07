from datetime import datetime, timedelta

from aiogram import Bot
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from database import Database


class ReminderService:
    def __init__(self, scheduler: AsyncIOScheduler, db: Database, bot: Bot) -> None:
        self.scheduler = scheduler
        self.db = db
        self.bot = bot

    async def send_reminder(self, booking_id: int) -> None:
        booking = self.db.get_booking_by_id(booking_id)
        if booking is None or booking["status"] != "active":
            return

        text = (
            f"Напоминаем, что {booking['child_name']} записан на занятие завтра "
            f"в {booking['slot_time']}. Ждем вас в центре MaksiUm! 🌟"
        )
        await self.bot.send_message(booking["user_id"], text)

    def schedule_for_booking(self, booking_id: int) -> None:
        booking = self.db.get_booking_by_id(booking_id)
        if booking is None or booking["status"] != "active":
            return

        lesson_dt = datetime.fromisoformat(f"{booking['slot_date']}T{booking['slot_time']}:00")
        reminder_dt = lesson_dt - timedelta(hours=24)
        now = datetime.now()
        if reminder_dt <= now:
            self.db.set_reminder(booking_id, None, None)
            return

        job_id = f"booking_reminder_{booking_id}"
        self.scheduler.add_job(
            self.send_reminder,
            trigger=DateTrigger(run_date=reminder_dt),
            kwargs={"booking_id": booking_id},
            id=job_id,
            replace_existing=True,
        )
        self.db.set_reminder(booking_id, job_id, reminder_dt.isoformat())

    def remove_for_booking(self, booking_id: int) -> None:
        booking = self.db.get_booking_by_id(booking_id)
        if booking is None:
            return
        job_id = booking["reminder_job_id"]
        if job_id:
            try:
                self.scheduler.remove_job(job_id=job_id)
            except JobLookupError:
                pass
        self.db.set_reminder(booking_id, None, None)

    def restore_jobs(self) -> None:
        for booking in self.db.get_future_active_bookings_with_reminders():
            reminder_at = datetime.fromisoformat(booking["reminder_at"])
            job_id = booking["reminder_job_id"] or f"booking_reminder_{booking['id']}"
            self.scheduler.add_job(
                self.send_reminder,
                trigger=DateTrigger(run_date=reminder_at),
                kwargs={"booking_id": int(booking["id"])},
                id=job_id,
                replace_existing=True,
            )
