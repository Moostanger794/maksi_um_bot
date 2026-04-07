from aiogram import Dispatcher

from .admin import router as admin_router
from .booking import router as booking_router
from .common import router as common_router


def setup_handlers(dp: Dispatcher) -> None:
    dp.include_router(common_router)
    dp.include_router(booking_router)
    dp.include_router(admin_router)
