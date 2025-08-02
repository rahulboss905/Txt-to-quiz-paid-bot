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
FREE_USER_LIMIT = 20
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
    """Enhanced HTTP handler for health checks and monitoring"""
    server_version = "TelegramQuizBot/6.0"
    
    def do_GET(self):
        try:
            start_time = time.time()
            client_ip = self.client_address[0]
            user_agent = self.headers.get('User-Agent', 'Unknown')
            
            logger.info(f"Health check request: {self.path} from {client_ip} ({user_agent})")
            
            if self.path in ['/', '/health', '/status']:
                response_text = "OK"
                content_type = "text/plain"
                
                if "Mozilla" in user_agent:
                    status = "🟢 Bot is running"
                    uptime = time.time() - self.server.start_time
                    hostname = socket.gethostname()
                    
                    total_users = users.count_documents({})
                    premium_count = premium_subscriptions.count_documents({
                        'expires_at': {'$gt': datetime.utcnow()}
                    })
                    
                    response_text = f"""
                    <!DOCTYPE html>
                    <html lang="en">
                    <head>
                        <meta charset="UTF-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        <title>Quiz Bot Status</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; margin: 20px; }}
                            .container {{ max-width: 800px; margin: 0 auto; }}
                            .status {{ font-size: 1.5em; font-weight: bold; color: #2ecc71; }}
                            .info {{ margin-top: 20px; padding: 15px; background-color: #f8f9fa; border-radius: 5px; }}
                            .stats {{ margin-top: 20px; padding: 15px; background-color: #e9f7fe; border-radius: 5px; }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>Telegram Quiz Bot Status</h1>
                            <div class="status">{status}</div>
                            
                            <div class="info">
                                <p><strong>Hostname:</strong> {hostname}</p>
                                <p><strong>Uptime:</strong> {uptime:.2f} seconds</p>
                                <p><strong>Version:</strong> 6.0 (Premium Features)</p>
                                <p><strong>Last Check:</strong> {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}</p>
                                <p><strong>Client IP:</strong> {client_ip}</p>
                                <p><strong>User Agent:</strong> {user_agent}</p>
                            </div>
                            
                            <div class="stats">
                                <h3>Bot Statistics</h3>
                                <p><strong>Total Users:</strong> {total_users}</p>
                                <p><strong>Premium Users:</strong> {premium_count}</p>
                            </div>
                            
                            <p style="margin-top: 30px;">
                                <a href="https://t.me/{BOT_USERNAME}" target="_blank">
                                    Contact the bot on Telegram
                                </a>
                            </p>
                        </div>
                    </body>
                    </html>
                    """
                    content_type = "text/html"
                
                response = response_text.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', content_type)
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                
                duration = (time.time() - start_time) * 1000
                logger.info(f"Health check passed - 200 OK - {duration:.2f}ms")
            else:
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'404 Not Found')
                logger.warning(f"Invalid path requested: {self.path}")
                
        except Exception as e:
            logger.error(f"Health check error: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'500 Internal Server Error')

    def log_message(self, format, *args):
        """Override to prevent default logging"""
        pass

def run_http_server(port=8080):
    try:
        server_address = ('0.0.0.0', port)
        httpd = HTTPServer(server_address, HealthCheckHandler)
        httpd.start_time = time.time()
        
        logger.info(f"HTTP server running on port {port}")
        httpd.serve_forever()
    except Exception as e:
        logger.critical(f"Failed to start HTTP server: {e}")
        time.sleep(5)
        run_http_server(port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    
    welcome_msg = (
        "🌟 *Welcome to Quiz Bot!* 🌟\n\n"
        "I can turn your text files into interactive 10-second quizzes!\n\n"
        "🔹 Use /createquiz - Start quiz creation\n"
        "🔹 Use /help - Show formatting guide\n"
        "🔹 Use /about - Bot information\n\n"
    )
    
    if premium:
        sub = premium_subscriptions.find_one({'user_id': user_id})
        expires = sub['expires_at'].strftime('%Y-%m-%d')
        welcome_msg += f"🎉 *PREMIUM USER* (Expires: {expires}) 🎉\nNo limits!\n\n"
    else:
        welcome_msg += (
            "ℹ️ *Free Account Limits:*\n"
            f"- Max {FREE_USER_LIMIT} questions per {COOLDOWN_MINUTES} minutes\n"
            "- Upgrade with /upgrade\n\n"
        )
    
    welcome_msg += "🔹 Use /myplan - Check your premium status\n"
    welcome_msg += "🔹 Use /plans - See available premium plans"
    
    contact_button = InlineKeyboardButton(
        "Contact Owner", 
        url=f"https://t.me/{OWNER_USERNAME}"
    )
    keyboard = [[contact_button]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_msg, 
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ====================== FIXED ABOUT COMMAND ======================
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot information - FIXED MARKDOWN"""
    try:
        # Using safe Markdown formatting without complex structures
        about_text = (
            "🤖 *Quiz Bot Pro*\n"
            "*Version*: 2.0 (MongoDB Edition)\n"
            f"*Creator*: [Rahul](https://t.me/{OWNER_USERNAME})\n\n"
            "✨ *Features*:\n"
            "- Create quizzes from text files\n"
            "- Premium subscriptions\n"
            "- 10-second timed polls\n\n"
            f"📣 *Support*: @{OWNER_USERNAME}\n"
            "📂 *Source*: github.com/your-repo"
        )
        
        contact_button = InlineKeyboardButton(
            "Contact Owner", 
            url=f"https://t.me/{OWNER_USERNAME}"
        )
        keyboard = [[contact_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Sending without Markdown to avoid formatting issues
        await update.message.reply_text(
            about_text, 
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in about_command: {e}")
        await update.message.reply_text("⚠️ An error occurred. Please try again later.")

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
            "/add <user_id> <duration> - Grant premium\n"
            "/rem <user_id> - Revoke premium\n"
            "/broadcast <message> - Broadcast to all users\n"
            "/setplan <name> <duration> <price> - Create premium plan\n"
        )
    
    help_text += "🔹 Use /myplan - Check your premium status\n"
    help_text += "🔹 Use /plans - See available premium plans"
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def create_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    user = get_user_data(user_id)
    
    if not premium:
        current_time = time.time()
        last_time = user.get('last_quiz_time', 0)
        time_diff = (current_time - last_time) / 60
        
        if time_diff >= COOLDOWN_MINUTES:
            update_user_data(user_id, {'quiz_count': 0, 'last_quiz_time': current_time})
            user['quiz_count'] = 0
        
        if user['quiz_count'] >= FREE_USER_LIMIT:
            remaining_time = COOLDOWN_MINUTES - int(time_diff)
            await update.message.reply_text(
                f"⏳ You've reached your free limit of {FREE_USER_LIMIT} questions.\n"
                f"Please wait {remaining_time} minutes or upgrade to /upgrade",
                parse_mode='Markdown'
            )
            return
    
    await update.message.reply_text(
        "📤 *Ready to create your quiz!*\n\n"
        "Please send me a .txt file containing your questions.\n\n"
        "Need format help? Use /help",
        parse_mode='Markdown'
    )

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add premium subscription (owner only)"""
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
            f"👋 ʜᴇʏ {firstname},\n"
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
    """Remove premium subscription (owner only)"""
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
                "👋 ʜᴇʏ {firstname},\n\n"
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
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    
    if premium:
        sub = premium_subscriptions.find_one({'user_id': user_id})
        expires = sub['expires_at'].strftime('%d-%m-%Y')
        await update.message.reply_text(
            f"🎉 You're a premium user! (Expires: {expires})\n"
            "Enjoy unlimited quiz generation!\n\n"
            "🔹 Use /myplan to see full details",
            parse_mode='Markdown'
        )
    else:
        all_plans = list(plans.find({}))
        
        if all_plans:
            plans_text = "\n\n📋 *Available Plans:*\n"
            for plan in all_plans:
                plans_text += f"• {plan['plan_name']}: {plan['duration']} - {plan['price']}\n"
        else:
            plans_text = ""
        
        contact_button = InlineKeyboardButton(
            "Contact Owner", 
            url=f"https://t.me/{OWNER_USERNAME}"
        )
        keyboard = [[contact_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🌟 *Upgrade to Premium!*\n\n"
            "Enjoy these benefits:\n"
            "✅ Unlimited quiz generation\n"
            "✅ No cooldown periods\n"
            "✅ Priority support\n\n"
            f"Use /plans to see available options{plans_text}\n\n"
            "Contact the owner to purchase:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

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
        "`/add <user_id> <duration>` - Add premium\n"
        "`/rem <user_id>` - Remove premium\n"
        "`/broadcast <message>` - Broadcast to all users\n"
        "`/setplan <name> <duration> <price>` - Create premium plan"
    )
    
    await update.message.reply_text(stats_msg, parse_mode='Markdown')

def parse_quiz_file(content: str) -> tuple:
    blocks = [b.strip() for b in content.split('\n\n') if b.strip()]
    valid_questions = []
    errors = []
    
    for i, block in enumerate(blocks, 1):
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        
        if len(lines) not in (6, 7):
            errors.append(f"❌ Question {i}: Invalid line count ({len(lines)}), expected 6 or 7")
            continue
            
        question = lines[0]
        options = lines[1:5]
        answer_line = lines[5]
        
        explanation = lines[6] if len(lines) == 7 else None
        
        answer_error = None
        if not answer_line.lower().startswith('answer:'):
            answer_error = "Missing 'Answer:' prefix"
        else:
            try:
                answer_num = int(answer_line.split(':')[1].strip())
                if not 1 <= answer_num <= 4:
                    answer_error = f"Invalid answer number {answer_num}"
            except (ValueError, IndexError):
                answer_error = "Malformed answer line"
        
        if answer_error:
            errors.append(f"❌ Q{i}: {answer_error}")
        else:
            option_texts = options
            correct_id = int(answer_line.split(':')[1].strip()) - 1
            valid_questions.append((question, option_texts, correct_id, explanation))
    
    return valid_questions, errors

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    user = get_user_data(user_id)
    
    if not update.message.document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Please send a .txt file")
        return
    
    try:
        file = await context.bot.get_file(update.message.document.file_id)
        await file.download_to_drive('quiz.txt')
        
        with open('quiz.txt', 'r', encoding='utf-8') as f:
            content = f.read()
        
        valid_questions, errors = parse_quiz_file(content)
        question_count = len(valid_questions)
        
        if not premium:
            current_time = time.time()
            last_time = user.get('last_quiz_time', 0)
            time_diff = (current_time - last_time) / 60
            
            if time_diff >= COOLDOWN_MINUTES:
                update_user_data(user_id, {'quiz_count': 0, 'last_quiz_time': current_time})
                user['quiz_count'] = 0
            
            if user['quiz_count'] + question_count > FREE_USER_LIMIT:
                remaining = FREE_USER_LIMIT - user['quiz_count']
                await update.message.reply_text(
                    f"⚠️ You can only create {remaining} more questions in this period.\n"
                    f"Upgrade to /upgrade for unlimited access.",
                    parse_mode='Markdown'
                )
                return
            
            new_count = user['quiz_count'] + question_count
            update_user_data(user_id, {
                'quiz_count': new_count,
                'last_quiz_time': current_time
            })
        
        if errors:
            error_msg = "\n".join(errors[:5])
            if len(errors) > 5:
                error_msg += f"\n\n...and {len(errors)-5} more errors"
            await update.message.reply_text(
                f"⚠️ Found {len(errors)} error(s):\n\n{error_msg}"
            )
        
        if valid_questions:
            status_msg = f"✅ Sending {len(valid_questions)} quiz question(s)..."
            if not premium:
                remaining = FREE_USER_LIMIT - (user['quiz_count'] if 'quiz_count' in user else 0)
                status_msg += f"\n\nℹ️ Free questions left: {remaining}"
            
            await update.message.reply_text(status_msg)
            
            for question, options, correct_id, explanation in valid_questions:
                try:
                    poll_params = {
                        "chat_id": update.effective_chat.id,
                        "question": question,
                        "options": options,
                        "type": 'quiz',
                        "correct_option_id": correct_id,
                        "is_anonymous": False,
                        "open_period": 10
                    }
                    
                    if explanation:
                        poll_params["explanation"] = explanation
                    
                    await context.bot.send_poll(**poll_params)
                except Exception as e:
                    logger.error(f"Poll send error: {str(e)}")
                    await update.message.reply_text("⚠️ Failed to send one quiz. Continuing...")
        else:
            await update.message.reply_text("❌ No valid questions found in file")
            
    except Exception as e:
        logger.error(f"File processing error: {str(e)}")
        await update.message.reply_text("⚠️ Error processing file. Please check format and try again.")

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

# ====================== FIXED PLANS COMMAND ======================
async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available premium plans - FIXED DATABASE ACCESS"""
    try:
        # Safely access the plans collection
        all_plans = list(plans.find({})) if plans else []
        
        if not all_plans:
            # Create contact button
            contact_button = InlineKeyboardButton(
                "Contact Owner", 
                url=f"https://t.me/{OWNER_USERNAME}"
            )
            keyboard = [[contact_button]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "ℹ️ No plans available yet. Contact owner for premium options.",
                reply_markup=reply_markup
            )
            return
        
        # Build plans text
        plans_text = "🌟 *Available Premium Plans* 🌟\n\n"
        for plan in all_plans:
            plan_name = plan.get('plan_name', 'Unknown Plan')
            duration = plan.get('duration', 'Unknown Duration')
            price = plan.get('price', 'Unknown Price')
            
            plans_text += (
                f"• *{plan_name}*\n"
                f"  Duration: {duration}\n"
                f"  Price: {price}\n\n"
            )
        
        # Create contact button
        contact_button = InlineKeyboardButton(
            "Contact Owner", 
            url=f"https://t.me/{OWNER_USERNAME}"
        )
        keyboard = [[contact_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        plans_text += "To purchase, contact the owner:"
        
        # Send without Markdown to avoid formatting issues
        await update.message.reply_text(
            plans_text,
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error in plans_command: {e}")
        await update.message.reply_text("⚠️ An error occurred. Please try again later.")

async def set_plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set premium plans (owner only)"""
    try:
        user_id = update.effective_user.id
        
        if user_id != OWNER_ID:
            await update.message.reply_text("❌ Owner only command!")
            return
        
        if len(context.args) < 3:
            await update.message.reply_text(
                "ℹ️ Usage: /setplan <plan_name> <duration> <price>\n"
                "Example: /setplan Basic \"30 days\" $5\n"
                "Example: /setplan Pro \"1 year\" $30"
            )
            return
        
        plan_name = context.args[0]
        duration = " ".join(context.args[1:-1])
        price = context.args[-1]
        
        # Update plans collection
        plans.update_one(
            {'plan_name': plan_name},
            {'$set': {
                'duration': duration,
                'price': price
            }},
            upsert=True
        )
        
        await update.message.reply_text(
            f"✅ Plan updated!\n\n"
            f"Plan Name: {plan_name}\n"
            f"Duration: {duration}\n"
            f"Price: {price}"
        )
    except Exception as e:
        logger.error(f"Error in set_plan_command: {e}")
        await update.message.reply_text("⚠️ An error occurred. Please check your input and try again.")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send message to all users (owner only)"""
    try:
        user_id = update.effective_user.id
        
        if user_id != OWNER_ID:
            await update.message.reply_text("❌ Owner only command!")
            return
        
        if not context.args:
            await update.message.reply_text("ℹ️ Usage: /broadcast <message>")
            return
        
        message = " ".join(context.args)
        total_users = users.count_documents({})
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data="broadcast_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        context.user_data['broadcast_message'] = message
        
        await update.message.reply_text(
            f"⚠️ Broadcast Confirmation\n\n"
            f"Message:\n{message}\n\n"
            f"Recipients: {total_users} users\n\n"
            "Are you sure you want to send?",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error in broadcast_command: {e}")
        await update.message.reply_text("⚠️ An error occurred. Please try again later.")

async def broadcast_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle broadcast confirmation button"""
    try:
        query = update.callback_query
        await query.answer()
        
        if query.data == "broadcast_cancel":
            await query.edit_message_text("🚫 Broadcast cancelled")
            return
        
        message = context.user_data.get('broadcast_message', "")
        if not message:
            await query.edit_message_text("❌ Broadcast message missing")
            return
        
        all_users = users.find({})
        total = all_users.count()
        success = 0
        failed = 0
        
        progress_msg = await query.edit_message_text(
            f"📤 Broadcasting to {total} users...\n0% complete"
        )
        
        for idx, user in enumerate(all_users, 1):
            try:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=f"📣 Broadcast Message\n\n{message}"
                )
                success += 1
            except Exception as e:
                logger.error(f"Broadcast to {user['user_id']} failed: {e}")
                failed += 1
            
            if idx % max(10, total//10) == 0 or idx == total:
                percent = int((idx/total)*100)
                try:
                    await progress_msg.edit_text(
                        f"📤 Broadcasting to {total} users...\n"
                        f"{percent}% complete ({idx}/{total})\n"
                        f"✅ Success: {success} ❌ Failed: {failed}"
                    )
                except:
                    pass
            
            time.sleep(0.1)
        
        await progress_msg.edit_text(
            f"✅ Broadcast complete!\n"
            f"• Total recipients: {total}\n"
            f"• Successfully sent: {success}\n"
            f"• Failed: {failed}"
        )
    except Exception as e:
        logger.error(f"Error in broadcast_button: {e}")
        await query.edit_message_text("⚠️ An error occurred during broadcast.")

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
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("createquiz", create_quiz))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("add", add_command))
    application.add_handler(CommandHandler("rem", rem_command))
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
