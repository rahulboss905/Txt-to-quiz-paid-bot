import os
import logging
import threading
from handlers.health import run_http_server
from handlers import register_handlers
from telegram.ext import Application

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Run the bot and HTTP server"""
    # Get port from environment (Render provides this)
    PORT = int(os.environ.get('PORT', 10000))
    logger.info(f"Starting HTTP server on port {PORT}")
    
    # Start HTTP server in a daemon thread
    http_thread = threading.Thread(target=run_http_server, args=(PORT,), daemon=True)
    http_thread.start()
    logger.info("HTTP server thread started")
    
    # Get token from environment
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TOKEN:
        logger.error("No TELEGRAM_TOKEN found in environment!")
        return
    
    # Create Telegram application
    application = Application.builder().token(TOKEN).build()
    
    # Register handlers
    register_handlers(application)
    
    # Start polling
    logger.info("Starting Telegram bot in polling mode...")
    application.run_polling()

if __name__ == '__main__':
    main()
