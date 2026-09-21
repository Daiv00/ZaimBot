import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
NOTIFY_CHAT_ID = int(os.getenv("NOTIFY_CHAT_ID", "0"))
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

COMPANY_NAME = os.getenv("COMPANY_NAME", "Название организации")
COMPANY_INN = os.getenv("COMPANY_INN", "")
COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/loan_uploads")
CONTRACT_DIR = os.getenv("CONTRACT_DIR", "/tmp/loan_contracts")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
