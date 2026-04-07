import os
from dataclasses import dataclass


@dataclass
class Config:
    bot_token: str
    admin_id: int
    channel_id: int
    channel_link: str
    gallery_url: str
    db_path: str


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise ValueError("BOT_TOKEN is not set in environment.")

    admin_id = int(os.getenv("ADMIN_ID", "0"))
    if admin_id <= 0:
        raise ValueError("ADMIN_ID must be a positive integer.")

    # If CHANNEL_ID is 0, channel checks/notifications are disabled.
    channel_id = int(os.getenv("CHANNEL_ID", "0"))

    return Config(
        bot_token=token,
        admin_id=admin_id,
        channel_id=channel_id,
        channel_link=os.getenv("CHANNEL_LINK", "https://t.me/your_channel"),
        gallery_url=os.getenv("GALLERY_URL", "https://www.instagram.com/maksium_tambov/"),
        db_path=os.getenv("DB_PATH", "maksium.db"),
    )
