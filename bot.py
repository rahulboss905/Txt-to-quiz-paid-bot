import os
import logging
import threading
import time
import socket
import re
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from pymongo import MongoClient, ReturnDocument

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
COOLDOWN_MINUTES = 10
FREE_USER_LIMIT = 10
OWNER_USERNAME = "Mr_rahul090"
IST = timezone(timedelta(hours=5, minutes=30))  # Indian Standard Time

# MongoDB setup
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
DB_NAME = 'quiz_bot'
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
users = db.users
premium_subscriptions = db.premium_subscriptions
plans = db.plans

# Ensure indexes
users.create_index('user_id', unique=True)
premium_subscriptions.create_index('user_id')
premium_subscriptions.create_index('expires_at', expireAfterSeconds=0)
plans.create_index('plan_name', unique=True)

# Load environment variables
OWNER_ID = int(os.getenv('OWNER_ID', 0))
BOT_USERNAME = os.getenv('BOT_USERNAME', 'your_bot')

# Helper functions
def get_user_data(user_id: int) -> dict:
    return users.find_one_and_update(
        {'user_id': user_id},
        {'$setOnInsert': {
            'quiz_count': 0,
            'last_quiz_time': 0
        }},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

def update_user_data(user_id: int, update: dict):
    users.update_one({'user_id': user_id}, {'$set': update})

def is_premium(user_id: int) -> bool:
    return bool(premium_subscriptions.find_one({
        'user_id': user_id,
        'expires_at': {'$gt': datetime.utcnow()}
    }))

def add_premium_subscription(user_id: int, duration: str):
    match = re.match(r'(\d+)\s*(day|month|year)s?', duration.lower())
    if not match:
        raise ValueError("Invalid duration format")
    
    quantity, unit = match.groups()
    quantity = int(quantity)
    
    if unit == 'day':
        expires_at = datetime.utcnow() + timedelta(days=quantity)
    elif unit == 'month':
        expires_at = datetime.utcnow() + timedelta(days=quantity*30)
    elif unit == 'year':
        expires_at = datetime.utcnow() + timedelta(days=quantity*365)
    else:
        raise ValueError("Unsupported time unit")
    
    premium_subscriptions.update_one(
        {'user_id': user_id},
        {'$set': {'expires_at': expires_at}},
        upsert=True
    )
    return expires_at

def format_ist(dt: datetime) -> tuple:
    """Convert UTC datetime to IST and format for display"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ist_dt = dt.astimezone(IST)
    date_str = ist_dt.strftime('%d-%m-%Y')
    time_str = ist_dt.strftime('%I:%M:%S %p').lstrip('0')
    return date_str, time_str

class HealthCheckHandler(BaseHTTPRequestHandler):
    # ... existing health check implementation ...

def run_http_server(port=8080):
    # ... existing HTTP server implementation ...

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... existing start command ...

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... existing about command ...

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    is_owner = user_id == OWNER_ID
    premium = is_premium(user_id)
    
    help_text = (
        "📝 *Quiz File Format Guide:*\n\n"
        "```\n"
        "What is 2+2?\n"
        "A) 3\n"
        "B) 4\n"
        "C) 5\n"
        "D) 6\n"
        "Answer: 2\n"
        "The correct answer is 4\n\n"
        "Python is a...\n"
        "A. Snake\n"
        "B. Programming language\n"
        "C. Coffee brand\n"
        "D. Movie\n"
        "Answer: 2\n"
        "```\n\n"
        "📌 *Rules:*\n"
        "• One question per block (separated by blank lines)\n"
        "• Exactly 4 options (any prefix format accepted)\n"
        "• Answer format: 'Answer: <1-4>' (1=first option, 2=second, etc.)\n"
        "• Optional 7th line for explanation (any text)\n\n"
    )
    
    if premium:
        help_text += "🎉 *Premium Status:* Active (No limits)\n\n"
    else:
        help_text += (
            "ℹ️ *Free Account Limits:*\n"
            f"- Max {FREE_USER_LIMIT} questions per {COOLDOWN_MINUTES} minutes\n"
            "- Remove limits with /upgrade\n\n"
        )
    
    if is_owner:
        help_text += (
            "👑 *Owner Commands:*\n"
            "/stats - Show bot statistics\n"
            "/add <user_id> <duration> - Grant premium\n"  # Updated command
            "/rem <user_id> - Revoke premium\n"  # Updated command
            "/broadcast <message> - Broadcast to all users\n"
            "/setplan <name> <duration> <price> - Create premium plan\n"
        )
    
    help_text += "🔹 Use /myplan - Check your premium status\n"
    help_text += "🔹 Use /plans - See available premium plans"
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ====================== UPDATED COMMANDS WITH IST TIME AND NEW NAMES ======================
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add premium subscription (owner only) - renamed from addpremium_command"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner only command!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("ℹ️ Usage: /add <user_id> <duration>\nExample: /add 123456 30day")
        return
    
    try:
        target_id = int(context.args[0])
        duration = " ".join(context.args[1:])
        expires_at = add_premium_subscription(target_id, duration)
        
        # Get current time in UTC
        now = datetime.utcnow()
        
        # Format dates in IST
        join_date, join_time = format_ist(now)
        expire_date, expire_time = format_ist(expires_at)
        duration_days = (expires_at - now).days
        
        premium_msg = (
            f"👋 ʜᴇʏ,\n"
            f"ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴘᴜʀᴄʜᴀꜱɪɴɢ ᴘʀᴇᴍɪᴜᴍ.\n"
            f"ᴇɴᴊᴏʏ !! ✨🎉\n\n"
            f"⏰ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ : {duration_days} day\n"
            f"⏳ ᴊᴏɪɴɪɴɢ ᴅᴀᴛᴇ : {join_date}\n"
            f"⏱️ ᴊᴏɪɴɪɴɢ ᴛɪᴍᴇ : {join_time}\n\n"
            f"⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {expire_date}\n"
            f"⏱️ ᴇxᴘɪʀʏ ᴛɪᴍᴇ : {expire_time}\n"
        )
        
        try:
            await context.bot.send_message(chat_id=target_id, text=premium_msg)
        except Exception as e:
            logger.warning(f"Couldn't notify user {target_id}: {e}")
            await update.message.reply_text(f"⚠️ Couldn't notify user: {e}")
        
        owner_msg = (
            f"✅ Premium added for user {target_id}\n"
            f"Expires: {expire_date}\n\n"
            f"Sent this to user:\n\n{premium_msg}"
        )
        await update.message.reply_text(owner_msg)
        
    except Exception as e:
        logger.error(f"Premium add error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def rem_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove premium subscription (owner only) - renamed from removepremium_command"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner only command!")
        return
    
    if not context.args:
        await update.message.reply_text("ℹ️ Usage: /rem <user_id>")
        return
    
    try:
        target_id = int(context.args[0])
        result = premium_subscriptions.delete_one({'user_id': target_id})
        
        if result.deleted_count > 0:
            removal_msg = (
                "👋 ʜᴇʏ,\n\n"
                "Your premium subscription has been removed.\n"
                "If you have any questions, contact support."
            )
            
            try:
                await context.bot.send_message(chat_id=target_id, text=removal_msg)
            except Exception as e:
                logger.warning(f"Couldn't notify user {target_id}: {e}")
                await update.message.reply_text(f"⚠️ Couldn't notify user: {e}")
            
            owner_msg = (
                f"✅ Premium removed for user {target_id}\n\n"
                f"Sent this to user:\n\n{removal_msg}"
            )
            await update.message.reply_text(owner_msg)
        else:
            await update.message.reply_text("ℹ️ User has no active premium")
    except Exception as e:
        logger.error(f"Premium remove error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... existing upgrade command ...

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner only command!")
        return
    
    total_users = users.count_documents({})
    active_premium = premium_subscriptions.count_documents({
        'expires_at': {'$gt': datetime.utcnow()}
    })
    
    active_today = users.count_documents({
        'last_quiz_time': {'$gt': time.time() - 86400}
    })
    
    total_quizzes = users.aggregate([
        {'$group': {'_id': None, 'total': {'$sum': '$quiz_count'}}}
    ])
    total_quiz_count = next(total_quizzes, {}).get('total', 0)
    
    stats_msg = (
        "📊 *Bot Statistics*\n\n"
        f"• Total Users: `{total_users}`\n"
        f"• Active Premium: `{active_premium}`\n"
        f"• Active Today: `{active_today}`\n"
        f"• Free Quizzes Generated: `{total_quiz_count}`\n\n"
        "👑 Owner Commands:\n"
        "`/add <user_id> <duration>` - Add premium\n"  # Updated
        "`/rem <user_id>` - Remove premium\n"  # Updated
        "`/broadcast <message>` - Broadcast to all users\n"
        "`/setplan <name> <duration> <price>` - Create premium plan"
    )
    
    await update.message.reply_text(stats_msg, parse_mode='Markdown')

# ... existing parse_quiz_file and handle_document functions ...

async def myplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    
    if premium:
        sub = premium_subscriptions.find_one({'user_id': user_id})
        expires_at = sub['expires_at']
        
        # Format dates in IST
        expire_date, expire_time = format_ist(expires_at)
        join_date, join_time = format_ist(expires_at - timedelta(days=(expires_at - datetime.utcnow()).days))
        remaining_days = (expires_at - datetime.utcnow()).days
        
        message = (
            "🌟 *Your Premium Plan* 🌟\n\n"
            f"👋 ʜᴇʏ,\n"
            f"ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴘᴜʀᴄʜᴀꜱɪɴɢ ᴘʀᴇᴍɪᴜᴍ.\n"
            f"ᴇɴᴊᴏʏ !! ✨🎉\n\n"
            f"⏰ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ : {remaining_days} day\n"
            f"⏳ ᴊᴏɪɴɪɴɢ ᴅᴀᴛᴇ : {join_date}\n"
            f"⏱️ ᴊᴏɪɴɪɴɢ ᴛɪᴍᴇ : {join_time}\n\n"
            f"⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {expire_date}\n"
            f"⏱️ ᴇxᴘɪʀʏ ᴛɪᴍᴇ : {expire_time}\n"
        )
        await update.message.reply_text(message, parse_mode='Markdown')
    else:
        upgrade_button = InlineKeyboardButton(
            "View Plans", 
            callback_data="view_plans"
        )
        contact_button = InlineKeyboardButton(
            "Contact Owner", 
            url=f"https://t.me/{OWNER_USERNAME}"
        )
        keyboard = [[upgrade_button, contact_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            "ℹ️ You do not have an active premium plan.\n\n"
            "Benefits of upgrading:\n"
            "✅ Unlimited quiz generation\n"
            "✅ No cooldown periods\n"
            "✅ Priority support\n\n"
            "Use /plans to see available options"
        )
        await update.message.reply_text(
            message, 
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

# ... existing plans_command, set_plan_command, broadcast_command, broadcast_button ...

def main() -> None:
    PORT = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting HTTP server on port {PORT}")
    
    http_thread = threading.Thread(target=run_http_server, args=(PORT,), daemon=True)
    http_thread.start()
    logger.info(f"HTTP server thread started")
    
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TOKEN:
        logger.error("No TELEGRAM_TOKEN found in environment!")
        return
    
    application = Application.builder().token(TOKEN).build()
    
    # Command handlers with updated command names
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("createquiz", create_quiz))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("add", add_command))  # Updated command name
    application.add_handler(CommandHandler("rem", rem_command))  # Updated command name
    application.add_handler(CommandHandler("upgrade", upgrade_command))
    application.add_handler(CommandHandler("myplan", myplan_command))
    application.add_handler(CommandHandler("plans", plans_command))
    application.add_handler(CommandHandler("setplan", set_plan_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(MessageHandler(filters.Document.TEXT, handle_document))
    
    # Callback handler
    application.add_handler(CallbackQueryHandler(broadcast_button, pattern="^broadcast_"))
    
    logger.info("Starting Telegram bot in polling mode...")
    application.run_polling()

if __name__ == '__main__':
    main()