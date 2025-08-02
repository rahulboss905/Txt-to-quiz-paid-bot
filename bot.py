import os
import logging
import threading
import time
import socket
import re
import json
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

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Enhanced HTTP handler for health checks and monitoring"""
    
    # Add server version identification
    server_version = "TelegramQuizBot/6.0"
    
    def do_GET(self):
        try:
            start_time = time.time()
            client_ip = self.client_address[0]
            user_agent = self.headers.get('User-Agent', 'Unknown')
            
            logger.info(f"Health check request: {self.path} from {client_ip} ({user_agent})")
            
            # Handle all valid endpoints
            if self.path in ['/', '/health', '/status']:
                # Simple plain text response for monitoring services
                response_text = "OK"
                content_type = "text/plain"
                
                # Detailed HTML response for browser requests
                if "Mozilla" in user_agent:  # Browser detection
                    status = "🟢 Bot is running"
                    uptime = time.time() - self.server.start_time
                    hostname = socket.gethostname()
                    
                    # Stats for status page
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
                
                # Send response
                response = response_text.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-type', content_type)
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
                
                # Log successful request
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
    """Run HTTP server in a separate thread"""
    try:
        server_address = ('0.0.0.0', port)
        httpd = HTTPServer(server_address, HealthCheckHandler)
        
        # Add start time to server instance
        httpd.start_time = time.time()
        
        logger.info(f"HTTP server running on port {port}")
        logger.info(f"Access URLs:")
        logger.info(f"  http://localhost:{port}/")
        logger.info(f"  http://localhost:{port}/health")
        logger.info(f"  http://localhost:{port}/status")
        
        httpd.serve_forever()
    except Exception as e:
        logger.critical(f"Failed to start HTTP server: {e}")
        # Attempt to restart after delay
        time.sleep(5)
        run_http_server(port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message and instructions"""
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

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot information"""
    about_text = (
        "🤖 *Quiz Bot Pro*\n"
        "*Version*: 2.0 (MongoDB Edition)\n"
        "*Creator*: @YourUsername\n\n"
        "✨ *Features*:\n"
        "- Create quizzes from text files\n"
        "- Premium subscriptions\n"
        "- 10-second timed polls\n\n"
        "📣 *Support*: @YourSupportChannel\n"
        "📂 *Source*: github.com/your-repo"
    )
    await update.message.reply_text(about_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed formatting instructions"""
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
    
    # Add premium info
    if premium:
        help_text += "🎉 *Premium Status:* Active (No limits)\n\n"
    else:
        help_text += (
            "ℹ️ *Free Account Limits:*\n"
            f"- Max {FREE_USER_LIMIT} questions per {COOLDOWN_MINUTES} minutes\n"
            "- Remove limits with /upgrade\n\n"
        )
    
    # Add owner commands
    if is_owner:
        help_text += (
            "👑 *Owner Commands:*\n"
            "/stats - Show bot statistics\n"
            "/addpremium <user_id> <duration> - Grant premium\n"
            "/removepremium <user_id> - Revoke premium\n"
        )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

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

async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show premium upgrade information"""
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    
    if premium:
        sub = premium_subscriptions.find_one({'user_id': user_id})
        expires = sub['expires_at'].strftime('%Y-%m-%d')
        await update.message.reply_text(
            f"🎉 You're a premium user! (Expires: {expires})\n"
            "Enjoy unlimited quiz generation!",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "🌟 *Upgrade to Premium!*\n\n"
            "Enjoy these benefits:\n"
            "✅ Unlimited quiz generation\n"
            "✅ No cooldown periods\n"
            "✅ Priority support\n\n"
            "Contact @admin to get premium access!",
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

def parse_quiz_file(content: str) -> tuple:
    """Parse and validate quiz content with flexible prefixes and full explanation"""
    blocks = [b.strip() for b in content.split('\n\n') if b.strip()]
    valid_questions = []
    errors = []
    
    for i, block in enumerate(blocks, 1):
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        
        # Basic validation - now accepts 6 or 7 lines
        if len(lines) not in (6, 7):
            errors.append(f"❌ Question {i}: Invalid line count ({len(lines)}), expected 6 or 7")
            continue
            
        question = lines[0]
        options = lines[1:5]
        answer_line = lines[5]
        
        # The entire 7th line is treated as explanation
        explanation = lines[6] if len(lines) == 7 else None
        
        # Validate answer format
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
        
        # Compile errors or add valid question
        if answer_error:
            errors.append(f"❌ Q{i}: {answer_error}")
        else:
            # Keep the full option text including prefixes
            option_texts = options
            correct_id = int(answer_line.split(':')[1].strip()) - 1
            valid_questions.append((question, option_texts, correct_id, explanation))
    
    return valid_questions, errors

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
                    f"Upgrade to /upgrade for unlimited access.",
                    parse_mode='Markdown'
                )
                return
            
            # Update user count
            new_count = user['quiz_count'] + question_count
            update_user_data(user_id, {
                'quiz_count': new_count,
                'last_quiz_time': current_time
            })
        
        # Report errors
        if errors:
            error_msg = "\n".join(errors[:5])
            if len(errors) > 5:
                error_msg += f"\n\n...and {len(errors)-5} more errors"
            await update.message.reply_text(
                f"⚠️ Found {len(errors)} error(s):\n\n{error_msg}"
            )
        
        # Send quizzes
        if valid_questions:
            status_msg = f"✅ Sending {len(valid_questions)} quiz question(s)..."
            if not premium:
                remaining = FREE_USER_LIMIT - user['quiz_count']
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
                        "open_period": 10  # 10-second quiz
                    }
                    
                    # Add explanation if provided
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

def main() -> None:
    """Run the bot and HTTP server"""
    # Get port from environment (Render provides this)
    PORT = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting HTTP server on port {PORT}")
    
    # Start HTTP server in a daemon thread
    http_thread = threading.Thread(target=run_http_server, args=(PORT,), daemon=True)
    http_thread.start()
    logger.info(f"HTTP server thread started")
    
    # Get token from environment
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TOKEN:
        logger.error("No TELEGRAM_TOKEN found in environment!")
        return
    
    # Create Telegram application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("about", about_command))
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
