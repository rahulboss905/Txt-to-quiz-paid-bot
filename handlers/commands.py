import os
import time
import re
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from utils.database import (
    get_user_data,
    update_user_data,
    is_premium,
    add_premium_subscription,
    get_bot_stats,
    get_premium_subscription
)
from utils.helpers import COOLDOWN_MINUTES, FREE_USER_LIMIT

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
OWNER_ID = int(os.getenv('OWNER_ID', 0))
BOT_USERNAME = os.getenv('BOT_USERNAME', 'your_bot')

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        sub = get_premium_subscription(user_id)
        if sub:
            expires = sub['expires_at'].strftime('%Y-%m-%d')
            welcome_msg += f"🎉 *PREMIUM USER* (Expires: {expires}) 🎉\nNo limits!\n\n"
    else:
        welcome_msg += (
            "ℹ️ *Free Account Limits:*\n"
            f"- Max {FREE_USER_LIMIT} questions per {COOLDOWN_MINUTES} minutes\n"
            "- Upgrade with /upgrade\n\n"
        )
    
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

# [Keep all other functions unchanged - including myplan_command and add_premium_command]
