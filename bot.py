import os
import logging
import threading
import time
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Enhanced HTTP handler for health checks and monitoring"""
    
    # Add server version identification
    server_version = "TelegramQuizBot/5.0"
    
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
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>Telegram Quiz Bot Status</h1>
                            <div class="status">{status}</div>
                            
                            <div class="info">
                                <p><strong>Hostname:</strong> {hostname}</p>
                                <p><strong>Uptime:</strong> {uptime:.2f} seconds</p>
                                <p><strong>Version:</strong> 5.0 (Full Explanation)</p>
                                <p><strong>Last Check:</strong> {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}</p>
                                <p><strong>Client IP:</strong> {client_ip}</p>
                                <p><strong>User Agent:</strong> {user_agent}</p>
                            </div>
                            
                            <p style="margin-top: 30px;">
                                <a href="https://t.me/{os.getenv('BOT_USERNAME', 'your_bot')}" target="_blank">
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
    await update.message.reply_text(
        "🌟 *Welcome to Quiz Bot!* 🌟\n\n"
        "I can turn your text files into interactive 10-second quizzes!\n\n"
        "🔹 Use /createquiz - Start quiz creation\n"
        "🔹 Use /help - Show formatting guide\n\n"
        "Let's make learning fun!",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed formatting instructions"""
    await update.message.reply_text(
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
        "• Optional 7th line for explanation (any text)",
        parse_mode='Markdown'
    )

async def create_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiate quiz creation process"""
    await update.message.reply_text(
        "📤 *Ready to create your quiz!*\n\n"
        "Please send me a .txt file containing your questions.\n\n"
        "Need format help? Use /help",
        parse_mode='Markdown'
    )

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
    """Process uploaded quiz file with flexible prefixes and full explanation"""
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
            await update.message.reply_text(
                f"✅ Sending {len(valid_questions)} quiz question(s)..."
            )
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
                    
                    # Add explanation if provided (entire 7th line)
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
    PORT = int(os.environ.get('PORT', 10000))  # Default to Render's port
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
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("createquiz", create_quiz))
    application.add_handler(MessageHandler(filters.Document.TEXT, handle_document))
    
    # Start polling
    logger.info("Starting Telegram bot in polling mode...")
    try:
        application.run_polling()
    except Exception as e:
        logger.critical(f"Telegram bot failed: {e}")
        # Attempt to restart after delay
        time.sleep(10)
        main()

if __name__ == '__main__':
    main()
