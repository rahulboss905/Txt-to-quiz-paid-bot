# ... existing imports ...
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ... existing constants and MongoDB setup ...

# Add new collection for plans
plans = db.plans
plans.create_index('plan_name', unique=True)

# ... existing helper functions ...

class HealthCheckHandler(BaseHTTPRequestHandler):
    # ... existing health check implementation ...

def run_http_server(port=8080):
    # ... existing HTTP server implementation ...

# ====================== NEW: BROADCAST COMMAND ======================
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send message to all users (owner only)"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ Owner only command!")
        return
    
    if not context.args:
        await update.message.reply_text("ℹ️ Usage: /broadcast <message>")
        return
    
    message = " ".join(context.args)
    all_users = users.find({})
    success = 0
    failed = 0
    
    # Create confirmation keyboard
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data="broadcast_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="broadcast_cancel"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Store message in context
    context.user_data['broadcast_message'] = message
    
    await update.message.reply_text(
        f"⚠️ *Broadcast Confirmation*\n\n"
        f"Message:\n`{message}`\n\n"
        f"Recipients: {all_users.count()} users\n\n"
        "Are you sure you want to send?",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def broadcast_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle broadcast confirmation button"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "broadcast_cancel":
        await query.edit_message_text("🚫 Broadcast cancelled")
        return
    
    # Get broadcast message from context
    message = context.user_data.get('broadcast_message', "")
    if not message:
        await query.edit_message_text("❌ Broadcast message missing")
        return
    
    # Send to all users
    all_users = users.find({})
    total = all_users.count()
    success = 0
    failed = 0
    
    # Update message with progress
    progress_msg = await query.edit_message_text(
        f"📤 Broadcasting to {total} users...\n0% complete"
    )
    
    # Send messages with rate limiting
    for idx, user in enumerate(all_users, 1):
        try:
            await context.bot.send_message(
                chat_id=user['user_id'],
                text=f"📣 *Broadcast Message*\n\n{message}",
                parse_mode='Markdown'
            )
            success += 1
        except Exception as e:
            logger.error(f"Broadcast to {user['user_id']} failed: {e}")
            failed += 1
        
        # Update progress every 10% or 10 users
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
        
        # Rate limiting
        time.sleep(0.1)
    
    # Final report
    await progress_msg.edit_text(
        f"✅ Broadcast complete!\n"
        f"• Total recipients: {total}\n"
        f"• Successfully sent: {success}\n"
        f"• Failed: {failed}"
    )

# ====================== NEW: PLAN MANAGEMENT ======================
async def set_plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set premium plans (owner only)"""
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
    
    # Save to database
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
        f"*Plan Name*: {plan_name}\n"
        f"*Duration*: {duration}\n"
        f"*Price*: {price}",
        parse_mode='Markdown'
    )

async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available premium plans"""
    all_plans = list(plans.find({}))
    
    if not all_plans:
        await update.message.reply_text("ℹ️ No plans available yet. Contact owner.")
        return
    
    plans_text = "🌟 *Available Premium Plans* 🌟\n\n"
    for plan in all_plans:
        plans_text += (
            f"• *{plan['plan_name']}*\n"
            f"  Duration: {plan['duration']}\n"
            f"  Price: {plan['price']}\n\n"
        )
    
    # Add contact button
    keyboard = [[InlineKeyboardButton("Contact Owner", url="https://t.me/Mr_rahul090")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    plans_text += "To purchase, contact the owner:"
    
    await update.message.reply_text(
        plans_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ====================== UPDATED COMMANDS WITH CONTACT BUTTON ======================
async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot information"""
    about_text = (
        "🤖 *Quiz Bot Pro*\n"
        "*Version*: 2.0 (MongoDB Edition)\n"
        "*Creator*: [Rahul](https://t.me/Mr_rahul090)\n\n"
        "✨ *Features*:\n"
        "- Create quizzes from text files\n"
        "- Premium subscriptions\n"
        "- 10-second timed polls\n\n"
        "📣 *Support*: @Mr_rahul090\n"
        "📂 *Source*: github.com/your-repo"
    )
    
    # Add contact button
    keyboard = [[InlineKeyboardButton("Contact Owner", url="https://t.me/Mr_rahul090")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        about_text, 
        parse_mode='Markdown',
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show premium upgrade information"""
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
        # Get available plans
        all_plans = list(plans.find({}))
        
        if all_plans:
            plans_text = "\n\n📋 *Available Plans:*\n"
            for plan in all_plans:
                plans_text += f"• {plan['plan_name']}: {plan['duration']} - {plan['price']}\n"
        else:
            plans_text = ""
        
        # Create contact button
        keyboard = [[InlineKeyboardButton("Contact Owner", url="https://t.me/Mr_rahul090")]]
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

# ... existing start_command, help_command, create_quiz, etc ...

async def myplan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's premium plan details"""
    user_id = update.effective_user.id
    premium = is_premium(user_id)
    
    if premium:
        sub = premium_subscriptions.find_one({'user_id': user_id})
        expires_at = sub['expires_at']
        
        # Format dates
        expire_date = expires_at.strftime('%d-%m-%Y')
        expire_time = expires_at.strftime('%I:%M:%S %p').lstrip('0')
        remaining_days = (expires_at - datetime.utcnow()).days
        
        # Get join date
        join_date = expires_at - timedelta(days=remaining_days)
        join_date_str = join_date.strftime('%d-%m-%Y')
        join_time_str = join_date.strftime('%I:%M:%S %p').lstrip('0')
        
        message = (
            "🌟 *Your Premium Plan* 🌟\n\n"
            f"👋 ʜᴇʏ,\n"
            f"ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴘᴜʀᴄʜᴀꜱɪɴɢ ᴘʀᴇᴍɪᴜᴍ.\n"
            f"ᴇɴᴊᴏʏ !! ✨🎉\n\n"
            f"⏰ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ : {remaining_days} day\n"
            f"⏳ ᴊᴏɪɴɪɴɢ ᴅᴀᴛᴇ : {join_date_str}\n"
            f"⏱️ ᴊᴏɪɴɪɴɢ ᴛɪᴍᴇ : {join_time_str}\n\n"
            f"⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {expire_date}\n"
            f"⏱️ ᴇxᴘɪʀʏ ᴛɪᴍᴇ : {expire_time}\n"
        )
    else:
        # Create upgrade button
        keyboard = [[InlineKeyboardButton("Upgrade Now", callback_data="upgrade")]]
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
        reply_markup=reply_markup if not premium else None
    )

# ... existing parse_quiz_file, handle_document ...

def main() -> None:
    """Run the bot and HTTP server"""
    # ... existing main function setup ...
    
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
    application.add_handler(CommandHandler("myplan", myplan_command))
    
    # NEW COMMANDS
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("setplan", set_plan_command))
    application.add_handler(CommandHandler("plans", plans_command))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(broadcast_button, pattern="^broadcast_"))
    
    # ... existing document handler ...
    
    # Start polling
    logger.info("Starting Telegram bot in polling mode...")
    application.run_polling()

if __name__ == '__main__':
    main()
