from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from config import Config
from keyboards.inline import check_subscription_kb, gallery_kb, main_menu_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, config: Config) -> None:
    is_admin = message.from_user.id == config.admin_id
    await message.answer(
        "Добро пожаловать в центр MaksiUm!\nВыберите действие:",
        reply_markup=main_menu_kb(is_admin=is_admin),
    )


@router.callback_query(F.data == "menu:main")
async def show_main_menu(callback: CallbackQuery, config: Config) -> None:
    is_admin = callback.from_user.id == config.admin_id
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=main_menu_kb(is_admin=is_admin),
    )
    await callback.answer()


@router.callback_query(F.data == "info:center")
async def center_info(callback: CallbackQuery, config: Config) -> None:
    is_admin = callback.from_user.id == config.admin_id
    await callback.message.edit_text(
        "MaksiUm - детский развивающий центр.\n"
        "Мы помогаем детям раскрывать таланты через современные занятия.\n"
        "Записывайтесь через бота и выбирайте удобное время!",
        reply_markup=main_menu_kb(is_admin=is_admin),
    )
    await callback.answer()


@router.callback_query(F.data == "info:prices")
async def prices_info(callback: CallbackQuery, config: Config) -> None:
    is_admin = callback.from_user.id == config.admin_id
    text = (
        "<b>Направления и цены:</b>\n\n"
        "🤖 Робототехника - 1200₽\n"
        "🎨 Изо-студия - 800₽\n"
        "🧠 Подготовка к школе - 1000₽"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=main_menu_kb(is_admin=is_admin))
    await callback.answer()


@router.callback_query(F.data == "info:gallery")
async def gallery(callback: CallbackQuery, config: Config) -> None:
    await callback.message.answer(
        f"Фотогалерея центра:\n{config.gallery_url}",
        disable_web_page_preview=True,
        reply_markup=gallery_kb(config.gallery_url),
    )
    await callback.answer()


@router.callback_query(F.data == "sub:check")
async def check_subscription(callback: CallbackQuery, config: Config) -> None:
    is_admin = callback.from_user.id == config.admin_id
    if config.channel_id == 0:
        await callback.message.answer(
            "Проверка подписки отключена в настройках бота.",
            reply_markup=main_menu_kb(is_admin=is_admin),
        )
        await callback.answer()
        return

    member = await callback.bot.get_chat_member(config.channel_id, callback.from_user.id)
    if member.status in {"member", "administrator", "creator"}:
        await callback.message.answer("Подписка подтверждена ✅")
        await callback.message.answer("Теперь можете записаться.", reply_markup=main_menu_kb(is_admin=is_admin))
    else:
        await callback.message.answer(
            "Подписка пока не найдена. Подпишитесь и попробуйте снова.",
            reply_markup=check_subscription_kb(config.channel_link),
        )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
