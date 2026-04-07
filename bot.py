import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import load_config
from database import Database
from handlers import setup_handlers
from middlewares import SubscriptionMiddleware
from scheduler.reminders import ReminderService


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    config = load_config()
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    db = Database(config.db_path)
    db.init()

    scheduler = AsyncIOScheduler()
    scheduler.start()

    reminders = ReminderService(scheduler=scheduler, db=db, bot=bot)
    reminders.restore_jobs()

    dp = Dispatcher(storage=MemoryStorage())
    dp.callback_query.middleware(SubscriptionMiddleware(config))
    setup_handlers(dp)

    # Ensure long polling receives updates even if webhook was previously set.
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except TelegramNetworkError as e:
        logging.warning("Could not delete webhook due to network error: %s", e)

    while True:
        try:
            await dp.start_polling(
                bot,
                config=config,
                db=db,
                reminders=reminders,
            )
            break
        except TelegramNetworkError as e:
            logging.error("Telegram network error: %s", e)
            logging.info("Retrying in 5 seconds...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
