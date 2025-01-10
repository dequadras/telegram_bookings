import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env file at the start
load_dotenv()


@dataclass
class BotConfig:
    TOKEN: str = os.environ.get("BOT_TOKEN", "")


@dataclass
class StripeConfig:
    API_KEY: str = os.environ.get("STRIPE_API_KEY", "")
    WEBHOOK_SECRET: str = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    PRICE_ID_MONTHLY: str = os.environ.get("STRIPE_PRICE_ID_MONTHLY", "")


@dataclass
class BookingConfig:
    FREE_TIER_LIMIT: int = 3
    BOOKING_START_HOUR: int = 7  # 7 AM
    TENIS_CLUB_URL: str = os.environ.get("TENIS_CLUB_URL", "")
    TENIS_CLUB_USERNAME: str = os.environ.get("TENIS_CLUB_USERNAME", "")
    TENIS_CLUB_PASSWORD: str = os.environ.get("TENIS_CLUB_PASSWORD", "")


@dataclass
class PayPalConfig:
    BUSINESS_EMAIL = "autobooking6@gmail.com"
    IPN_URL = "https://your-domain.com/paypal-ipn"  # URL that will handle PayPal IPN notifications


CONFIG = {"bot": BotConfig(), "stripe": StripeConfig(), "booking": BookingConfig(), "paypal": PayPalConfig()}
