import nest_asyncio
nest_asyncio.apply()

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Import Motor for asynchronous MongoDB access
from motor.motor_asyncio import AsyncIOMotorClient
from config import BOT1_TOKEN, ADMIN1_IDS, MONGO_URI1, MONGO_DB_NAME1

# Bot configuration


mongo_client = pymongo.MongoClient(MONGO_URI1)
db = mongo_client[MONGO_DB_NAME1]
db = mongo_client["websiteDB"]  # You can change the database name if needed
websites_collection = db["websites"]  # Collection to store website URLs

# In-memory dictionary to store website status info (ephemeral)
website_status = {}  # {website: {"last_status": str, "last_open": datetime, "next_open": datetime}}

# Conversation state for adding website
WAITING_FOR_URL = 1

async def get_websites():
    """Fetches the list of websites from MongoDB."""
    docs = await websites_collection.find({}).to_list(length=None)
    return [doc["url"] for doc in docs]

async def check_websites(session: aiohttp.ClientSession):
    """
    Background task: Every 10 seconds, attempts to open each website in the DB.
    Updates website_status with the HTTP status or error message.
    """
    global website_status
    while True:
        now = datetime.now()
        urls = await get_websites()
        for site in urls:
            try:
                async with session.get(site) as response:
                    status_code = response.status
                    website_status[site] = {
                        "last_status": f"HTTP {status_code}",
                        "last_open": now,
                        "next_open": now + timedelta(seconds=10),
                    }
            except Exception as e:
                website_status[site] = {
                    "last_status": f"Error: {str(e)}",
                    "last_open": now,
                    "next_open": now + timedelta(seconds=10),
                }
        await asyncio.sleep(10)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /status command: Replies with the status of each website.
    Only responds if the sender is the admin.
    """
    if update.effective_user.id != ADMIN1_IDS:
        return
    msg = "Website status:\n"
    for site, stat in website_status.items():
        last_status = stat.get("last_status", "N/A")
        last_open = stat.get("last_open")
        next_open = stat.get("next_open")
        last_open_str = last_open.strftime("%Y-%m-%d %H:%M:%S") if last_open else "N/A"
        next_open_str = next_open.strftime("%Y-%m-%d %H:%M:%S") if next_open else "N/A"
        msg += (f"{site}:\n"
                f"   Last Status: {last_status}\n"
                f"   Last Open: {last_open_str}\n"
                f"   Next Open: {next_open_str}\n")
    await update.message.reply_text(msg)

async def website(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /website command: Shows current websites with an inline button to add a new website.
    Only responds if the sender is the admin.
    """
    if update.effective_user.id != ADMIN1_IDS:
        return
    urls = await get_websites()
    keyboard = [[InlineKeyboardButton("Add Website", callback_data="add_website")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "Current websites:\n" + "\n".join(urls) if urls else "No websites added yet."
    await update.message.reply_text(text, reply_markup=reply_markup)

async def add_website_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback for the "Add Website" inline button.
    Sends a new message prompting the admin to send the website link, with an inline Cancel button.
    """
    if update.effective_user.id != ADMIN1_IDS:
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    cancel_keyboard = [[InlineKeyboardButton("Cancel", callback_data="cancel_add")]]
    cancel_markup = InlineKeyboardMarkup(cancel_keyboard)
    await update.effective_chat.send_message("Please send the website link you want to add:", reply_markup=cancel_markup)
    return WAITING_FOR_URL

async def cancel_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Callback for the inline Cancel button during the add website process.
    Cancels the add website conversation.
    """
    if update.effective_user.id != ADMIN1_IDS:
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    await update.effective_chat.send_message("Add website operation cancelled.")
    return ConversationHandler.END

async def add_website_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receives the website link from the admin, adds it to the MongoDB collection,
    and resends the updated website list message.
    """
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    url = update.message.text.strip()
    # Check if the website already exists
    existing = await websites_collection.find_one({"url": url})
    if existing:
        await update.message.reply_text(f"Website {url} is already in the list.")
    else:
        await websites_collection.insert_one({"url": url})
        await update.message.reply_text(f"Website {url} added successfully!")
    # Resend the updated website list message
    urls = await get_websites()
    keyboard = [[InlineKeyboardButton("Add Website", callback_data="add_website")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "Current websites:\n" + "\n".join(urls)
    await update.effective_chat.send_message(text, reply_markup=reply_markup)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancels the add website conversation.
    """
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def remove_website(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /remove command: Removes the specified website from the MongoDB collection.
    The admin should send the command as /remove {website_url}.
    After removal, the bot resends the updated website list.
    """
    if update.effective_user.id != ADMIN1_IDS:
        return
    if not context.args:
        await update.message.reply_text("Usage: /remove {website_url}")
        return
    url = " ".join(context.args).strip()
    result = await websites_collection.delete_one({"url": url})
    if result.deleted_count:
        await update.message.reply_text(f"Website {url} removed successfully!")
        # Also remove from in-memory status if exists
        website_status.pop(url, None)
    else:
        await update.message.reply_text(f"Website {url} not found in the list.")
    
    # Resend the updated website list message
    urls = await get_websites()
    keyboard = [[InlineKeyboardButton("Add Website", callback_data="add_website")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "Current websites:\n" + "\n".join(urls) if urls else "No websites added yet."
    await update.message.reply_text(text, reply_markup=reply_markup)

async def main():
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Build the application
    application = ApplicationBuilder().token(BOT1_TOKEN).build()

    # Conversation handler for adding a website
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_website_callback, pattern="^add_website$")],
        states={
            WAITING_FOR_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_website_url),
                CallbackQueryHandler(cancel_add_callback, pattern="^cancel_add$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Register command and conversation handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("website", website))
    application.add_handler(CommandHandler("remove", remove_website))

    # Create an aiohttp session and start the background task for website checking
    session = aiohttp.ClientSession()
    asyncio.create_task(check_websites(session))

    # Start the bot
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
