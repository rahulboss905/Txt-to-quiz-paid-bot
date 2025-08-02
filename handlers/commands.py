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

# [Keep all other existing command functions unchanged]
