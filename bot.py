import os
import logging
import threading
import time
import socket
import re
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
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

# MongoDB setup
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
DB_NAME = 'quiz_bot'
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
users = db.users
premium_subscriptions = db.premium_subscriptions

# Ensure indexes
users.create_index('user_id', unique=True)
premium_subscriptions.create_index('user_id')
premium_subscriptions.create_index('expires_at', expireAfterSeconds=0)

# Load environment variables
OWNER_ID = int(os.getenv('OWNER_ID', 0))
BOT_USERNAME = os.getenv('BOT_USERNAME', 'your_bot')

# Helper functions
def get_user_data(user_id: int) -> dict:
    """Get or create user data"""
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
    """Update user data"""
    users.update_one({'user_id': user_id}, {'$set': update})

def is_premium(user_id: int) -> bool:
    """Check if user has active premium subscription"""
    return bool(premium_subscriptions.find_one({
        'user_id': user_id,
        'expires_at': {'$gt': datetime.utcnow()}
    }))

def add_premium_subscription(user_id: int, duration: str):
    """Add premium subscription with duration"""
    # Parse duration
    match = re.match(r'(\d+)\s*(day|month|year)s?', duration.lower())
    if not match:
        raise ValueError("Invalid duration format")
    
    quantity, unit = match.groups()
    quantity = int(quantity)
    
    # Calculate expiration
    if unit == 'day':
        expires_at = datetime.utcnow() + timedelta(days=quantity)
    elif unit == 'month':
        expires_at = datetime.utcnow() + timedelta(days=quantity*30)
    elif unit == 'year':
        expires_at = datetime.utcnow() + timedelta(days=quantity*365)
    else:
        raise ValueError("Unsupported time unit")
    
    # Upsert subscription
    premium_subscriptions.update_one(
        {'user_id': user_id},
        {'$set': {'expires_at': expires_at}},
        upsert=True
    )
    return expires_at

# Existing HealthCheckHandler remains unchanged
# ... [Keep the existing HealthCheckHandler implementation] ...

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    
    welcome_msg = (
        "🌟 *Welcome to Quiz Bot!* 🌟\n\n"
        "I can turn your text files into interactive 10-second quizzes!\n\n"
        "🔹 Use /createquiz - Start quiz creation\n"
        "🔹 Use /help - Show formatting guide\n\n"
    )
    
    if premium:
        # Get expiration date
        sub = premium_subscriptions.find_one({'user_id': user_id})
        expires = sub['expires_at'].strftime('%Y-%m-%d')
        welcome_msg += f"🎉 *PREMIUM USER* (Expires: {expires}) 🎉\nNo limits!\n\n"
    else:
        welcome_msg += (
            "ℹ️ *Free Account Limits:*\n"
            f"- Max {FREE_USER_LIMIT} questions per {COOLDOWN_MINUTES} minutes\n"
            "- Upgrade with /upgrade\n\n"
        )
    
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def add_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add premium subscription (owner only)"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner only command!")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("ℹ️ Usage: /addpremium <user_id> <duration>\nExample: /addpremium 123456 30day")
        return
    
    try:
        target_id = int(context.args[0])
        duration = " ".join(context.args[1:])
        expires_at = add_premium_subscription(target_id, duration)
        
        await update.message.reply_text(
            f"✅ Premium added for user {target_id}\n"
            f"Expires: {expires_at.strftime('%Y-%m-%d')}"
        )
    except Exception as e:
        logger.error(f"Premium add error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def remove_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove premium subscription (owner only)"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner only command!")
        return
    
    if not context.args:
        await update.message.reply_text("ℹ️ Usage: /removepremium <user_id>")
        return
    
    try:
        target_id = int(context.args[0])
        result = premium_subscriptions.delete_one({'user_id': target_id})
        
        if result.deleted_count > 0:
            await update.message.reply_text(f"✅ Premium removed for user {target_id}")
        else:
            await update.message.reply_text("ℹ️ User has no active premium")
    except Exception as e:
        logger.error(f"Premium remove error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def create_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiate quiz creation process"""
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    user = get_user_data(user_id)
    
    # Check free user limits
    if not premium:
        current_time = time.time()
        last_time = user.get('last_quiz_time', 0)
        time_diff = (current_time - last_time) / 60  # in minutes
        
        # Reset count if cooldown period passed
        if time_diff >= COOLDOWN_MINUTES:
            update_user_data(user_id, {'quiz_count': 0, 'last_quiz_time': current_time})
            user['quiz_count'] = 0
        
        # Check if user exceeded limit
        if user['quiz_count'] >= FREE_USER_LIMIT:
            remaining_time = COOLDOWN_MINUTES - int(time_diff)
            await update.message.reply_text(
                f"⏳ You've reached your free limit of {FREE_USER_LIMIT} questions.\n"
                f"Please wait {remaining_time} minutes or upgrade to /premium",
                parse_mode='Markdown'
            )
            return
    
    await update.message.reply_text(
        "📤 *Ready to create your quiz!*\n\n"
        "Please send me a .txt file containing your questions.\n\n"
        "Need format help? Use /help",
        parse_mode='Markdown'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot statistics (owner only)"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner only command!")
        return
    
    # Get stats
    total_users = users.count_documents({})
    active_premium = premium_subscriptions.count_documents({
        'expires_at': {'$gt': datetime.utcnow()}
    })
    
    # Active today (last 24 hours)
    active_today = users.count_documents({
        'last_quiz_time': {'$gt': time.time() - 86400}
    })
    
    # Free quizzes generated
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
        "`/addpremium <user_id> <duration>` - Add premium\n"
        "`/removepremium <user_id>` - Remove premium"
    )
    
    await update.message.reply_text(stats_msg, parse_mode='Markdown')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process uploaded quiz file"""
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    user = get_user_data(user_id)
    
    # Check file type
    if not update.message.document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Please send a .txt file")
        return
    
    try:
        # Download file
        file = await context.bot.get_file(update.message.document.file_id)
        await file.download_to_drive('quiz.txt')
        
        with open('quiz.txt', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse and validate
        valid_questions, errors = parse_quiz_file(content)
        question_count = len(valid_questions)
        
        # Apply free user limits
        if not premium:
            current_time = time.time()
            last_time = user.get('last_quiz_time', 0)
            time_diff = (current_time - last_time) / 60
            
            # Reset count if cooldown period passed
            if time_diff >= COOLDOWN_MINUTES:
                update_user_data(user_id, {'quiz_count': 0, 'last_quiz_time': current_time})
                user['quiz_count'] = 0
            
            # Check if user would exceed limit
            if user['quiz_count'] + question_count > FREE_USER_LIMIT:
                remaining = FREE_USER_LIMIT - user['quiz_count']
                await update.message.reply_text(
                    f"⚠️ You can only create {remaining} more questions in this period.\n"
                    f"Upgrade to /premium for unlimited access.",
                    parse_mode='Markdown'
                )
                return
            
            # Update user count
            new_count = user['quiz_count'] + question_count
            update_user_data(user_id, {
                'quiz_count': new_count,
                'last_quiz_time': current_time
            })
        
        # ... [rest of handle_document remains unchanged] ...
        # Report errors and send quizzes
        # ...
        
    except Exception as e:
        logger.error(f"File processing error: {str(e)}")
        await update.message.reply_text("⚠️ Error processing file. Please check format and try again.")

# ... [Keep the rest of the existing code including parse_quiz_file] ...

def main() -> None:
    """Run the bot and HTTP server"""
    PORT = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting HTTP server on port {PORT}")
    
    # Start HTTP server in a daemon thread
    http_thread = threading.Thread(target=run_http_server, args=(PORT,), daemon=True)
    http_thread.start()
    
    # Get token from environment
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TOKEN:
        logger.error("No TELEGRAM_TOKEN found in environment!")
        return
    
    # Create Telegram application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("createquiz", create_quiz))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("addpremium", add_premium_command))
    application.add_handler(CommandHandler("removepremium", remove_premium_command))
    application.add_handler(CommandHandler("upgrade", upgrade_command))
    application.add_handler(MessageHandler(filters.Document.TEXT, handle_document))
    
    # Start polling
    logger.info("Starting Telegram bot in polling mode...")
    application.run_polling()

if __name__ == '__main__':
    main()
