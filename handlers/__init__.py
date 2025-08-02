from .commands import (
    start_command,
    about_command,
    help_command,
    create_quiz_command,
    stats_command,
    add_premium_command,
    remove_premium_command,
    upgrade_command
)
from .documents import handle_document
from telegram.ext import CommandHandler, MessageHandler, filters

def register_handlers(application):
    """Register all handlers with the application"""
    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("createquiz", create_quiz_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("addpremium", add_premium_command))
    application.add_handler(CommandHandler("removepremium", remove_premium_command))
    application.add_handler(CommandHandler("upgrade", upgrade_command))
    
    # Document handler
    application.add_handler(MessageHandler(filters.Document.TEXT, handle_document))
