import re
import logging
from telegram import Update
from telegram.ext import CommandHandler, Application, ContextTypes

# Initialize logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Text sanitization utility
def safe_format(text: str) -> str:
    """Removes all Markdown/HTML formatting while preserving content"""
    # Convert markdown links to plain text
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", text)
    
    # Escape all special characters
    text = re.sub(r"([*_~`>#|=+-])", r"\\\1", text)
    
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    
    # Prevent excessive line breaks
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    return text.strip()

# Unified message sender with error handling
async def send_safe_message(update: Update, text: str, max_length=4000):
    """Safely sends messages with formatting protection and chunking"""
    try:
        # Apply safety formatting
        safe_text = safe_format(text)
        
        # Split long messages
        if len(safe_text) > max_length:
            chunks = [safe_text[i:i+max_length] for i in range(0, len(safe_text), max_length)]
            for chunk in chunks:
                await update.message.reply_text(
                    text=chunk,
                    parse_mode=None,  # Critical: disable formatting
                    disable_web_page_preview=True
                )
        else:
            await update.message.reply_text(
                text=safe_text,
                parse_mode=None,
                disable_web_page_preview=True
            )
        return True
    except Exception as e:
        logger.error(f"Message send failed: {str(e)}")
        try:
            # Ultimate fallback
            await update.message.reply_text(
                "⚠️ Message delivery issue. Contact: support@studymate.app",
                parse_mode=None
            )
        except:
            logger.critical("Complete message failure")
        return False

# Content generators with safeguards
def generate_plan_content():
    """Safe content generator for /plan command"""
    content = """
    Study Mate Premium Plans (Updated 2025)
    
    BASIC: $10/month
    - 50 queries/day
    - Core features
    
    PRO: $20/month
    - Unlimited queries
    - Priority support
    - Early access features
    
    Special Offer: Save 20% with annual billing!
    Contact: billing@studymate.app
    """
    # Remove any accidental formatting
    return re.sub(r"([*_~`])", "", content)

def generate_about_content():
    """Simplified about content"""
    return """
    Study Mate - AI Learning Companion
    Version: 2.4.1
    Premium Status: Active
    Contact: support@studymate.app
    """

def generate_help_content():
    """Safe help content"""
    return """
    Study Mate Help:
    /start - Begin session
    /plan - View subscriptions
    /about - App information
    /help - Show this message
    """

# Command handlers using safe sender
async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_safe_message(update, generate_plan_content())

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_safe_message(update, generate_about_content())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_safe_message(update, generate_help_content())

# Application setup
def main():
    TOKEN = "7233974422:AAGy7NFIxxUen8tJM6TjNh5uTxRxIcpkk-E"    # Replace with actual token
    
    application = Application.builder().token(TOKEN).build()
    
    # Register commands
    application.add_handler(CommandHandler("plan", plan_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()
