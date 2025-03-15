import os

# Bot tokens (set these in your environment variables)
BOT1_TOKEN = os.environ["BOT1_TOKEN"]
BOT2_TOKEN = os.environ["BOT2_TOKEN"]

# Admin IDs as a list of integers (comma-separated string in environment variable)
#ADMIN1_IDS = [int(admin_id.strip()) for admin_id in os.environ.get("ADMIN_IDS", "").split(",") if admin_id.strip()]
ADMIN1_IDS = int(os.environ.get("ADMIN_ID", "6773787379"))

# Web server configuration
WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("WEB_PORT", 8080))
