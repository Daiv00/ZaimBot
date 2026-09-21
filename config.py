import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Telegram chat where every application is sent.
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# Optional: comma-separated Telegram user IDs allowed to use admin commands.
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

COMPANY_NAME = os.getenv("COMPANY_NAME", "Компания")
COMPANY_INN = os.getenv("COMPANY_INN", "")
COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "")

RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()

UPLOAD_DIR = "/tmp/loan_uploads"
CONTRACT_DIR = "/tmp/loan_contracts"
