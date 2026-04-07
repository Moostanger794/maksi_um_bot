from aiogram.fsm.state import State, StatesGroup


class BookingFSM(StatesGroup):
    waiting_parent_and_child = State()
    waiting_phone = State()
