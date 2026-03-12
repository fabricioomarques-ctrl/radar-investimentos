import os

BOT_NAME = "Radar de Investimentos PRO"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "5"))

SELIC = float(os.getenv("FIXED_SELIC_ANNUAL", "10.75"))
CDI = float(os.getenv("FIXED_CDI_ANNUAL", "10.65"))
