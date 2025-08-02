import logging
import time
from telegram import Update
from telegram.ext import ContextTypes
from utils.database import (
    get_user_data,
    update_user_data,
    is_premium
)
from utils.parser import parse_quiz_file
from utils.helpers import FREE_USER_LIMIT, COOLDOWN_MINUTES

logger = logging.getLogger(__name__)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
