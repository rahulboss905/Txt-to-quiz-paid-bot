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

async def myplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    
    if not premium:
        await update.message.reply_text("ℹ️ You don't have an active premium subscription")
        return
    
    # Get subscription details
    sub = premium_subscriptions.find_one({'user_id': user_id})
    if not sub:
        await update.message.reply_text("❌ Premium details not found")
        return
    
    # Format dates
    now = datetime.utcnow()
    join_date = sub['created_at'].strftime("%d-%m-%Y")
    join_time = sub['created_at'].strftime("%I:%M:%S %p")
    expiry_date = sub['expires_at'].strftime("%d-%m-%Y")
    expiry_time = sub['expires_at'].strftime("%I:%M:%S %p")
    
    # Calculate remaining days
    remaining_days = (sub['expires_at'] - now).days
    
    # Format message
    message = (
        f"👋 ʜᴇʏ {update.effective_user.first_name},\n"
        f"🌟 *Your Premium Plan* 🌟\n\n"
        f"⏰ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ : {remaining_days} days remaining\n"
        f"⏳ ᴊᴏɪɴɪɴɢ ᴅᴀᴛᴇ : {join_date}\n"
        f"⏱️ ᴊᴏɪɴɪɴɢ ᴛɪᴍᴇ : {join_time}\n\n"
        f"⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {expiry_date}\n"
        f"⏱️ ᴇxᴘɪʀʏ ᴛɪᴍᴇ : {expiry_time}"
    )
    
    await update.message.reply_text(message, parse_mode='Markdown')

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
        
        # Get current datetime
        now = datetime.utcnow()
        join_date = now.strftime("%d-%m-%Y")
        join_time = now.strftime("%I:%M:%S %p")
        expiry_date = expires_at.strftime("%d-%m-%Y")
        expiry_time = expires_at.strftime("%I:%M:%S %p")
        
        # Calculate duration in days
        duration_days = (expires_at - now).days
        
        # Format user message
        user_msg = (
            f"👋 ʜᴇʏ user,\n"
            f"ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴘᴜʀᴄʜᴀꜱɪɴɢ ᴘʀᴇᴍɪᴜᴍ.\n"
            f"ᴇɴᴊᴏʏ !! ✨🎉\n\n"
            f"⏰ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ : {duration_days} day\n"
            f"⏳ ᴊᴏɪɴɪɴɢ ᴅᴀᴛᴇ : {join_date}\n"
            f"⏱️ ᴊᴏɪɴɪɴɢ ᴛɪᴍᴇ : {join_time}\n\n"
            f"⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {expiry_date}\n"
            f"⏱️ ᴇxᴘɪʀʏ ᴛɪᴍᴇ : {expiry_time}"
        )
        
        # Try to send to user
        try:
            await context.bot.send_message(chat_id=target_id, text=user_msg)
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")
        
        # Send confirmation to owner
        owner_msg = (
            f"✅ Premium added for user {target_id}\n"
            f"Expires: {expiry_date} at {expiry_time}\n\n"
            "User notification:\n"
            f"{user_msg}"
        )
        await update.message.reply_text(owner_msg)
        
    except Exception as e:
        logger.error(f"Premium add error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

# [Keep all other existing command functions unchanged]    await update.message.reply_text(help_text, parse_mode='Markdown')

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
