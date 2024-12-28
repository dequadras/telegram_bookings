import os
from dataclasses import dataclass
from typing import Dict

@dataclass
class BotConfig:
    TOKEN: str = os.environ.get('BOT_TOKEN', '')
    
@dataclass
class StripeConfig:
    API_KEY: str = os.environ.get('STRIPE_API_KEY', '')
    WEBHOOK_SECRET: str = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    PRICE_ID_MONTHLY: str = os.environ.get('STRIPE_PRICE_ID_MONTHLY', '')
    
@dataclass
class BookingConfig:
    FREE_TIER_LIMIT: int = 3
    BOOKING_START_HOUR: int = 7  # 7 AM
    TENNIS_CLUB_URL: str = os.environ.get('TENNIS_CLUB_URL', '')
    TENNIS_CLUB_USERNAME: str = os.environ.get('TENNIS_CLUB_USERNAME', '')
    TENNIS_CLUB_PASSWORD: str = os.environ.get('TENNIS_CLUB_PASSWORD', '')

CONFIG = {
    "bot": BotConfig(),
    "stripe": StripeConfig(),
    "booking": BookingConfig()
} 