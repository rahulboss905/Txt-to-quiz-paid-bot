import os
import time
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from utils.database import (
    get_user_data,
    update_user_data,
    is_premium,
    add_premium_subscription,
    get_bot_stats
)
from utils.helpers import COOLDOWN_MINUTES, FREE_USER_LIMIT

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

async def create_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    user = get_user_data(user_id)
    
    # Check free user limits
    if not premium:
        current_time = time.time()
        last_time = user.get('last_quiz_time', 0)
        time_diff = (current_time - last_time) / 60
        
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
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner only command!")
        return
    
    # Get stats
    stats = get_bot_stats()
    
    stats_msg = (
        "📊 *Bot Statistics*\n\n"
        f"• Total Users: `{stats['total_users']}`\n"
        f"• Active Premium: `{stats['active_premium']}`\n"
        f"• Active Today: `{stats['active_today']}`\n"
        f"• Free Quizzes Generated: `{stats['total_quiz_count']}`\n\n"
        "👑 Owner Commands:\n"
        "`/addpremium <user_id> <duration>` - Add premium\n"
        "`/removepremium <user_id>` - Remove premium"
    )
    
    await update.message.reply_text(stats_msg, parse_mode='Markdown')
