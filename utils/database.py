import os
import logging
import re
import time  # Added for get_bot_stats function
from datetime import datetime, timedelta
from pymongo import MongoClient, ReturnDocument

logger = logging.getLogger(__name__)

# MongoDB setup
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017')
DB_NAME = 'quiz_bot'
client = MongoClient(MONGODB_URI)
db = client[DB_NAME]
users = db.users
premium_subscriptions = db.premium_subscriptions

# Ensure indexes
users.create_index('user_id', unique=True)
premium_subscriptions.create_index('user_id')
premium_subscriptions.create_index('expires_at', expireAfterSeconds=0)

def get_user_data(user_id: int) -> dict:
    """Get or create user data"""
    return users.find_one_and_update(
        {'user_id': user_id},
        {'$setOnInsert': {
            'quiz_count': 0,
            'last_quiz_time': 0
        }},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

def update_user_data(user_id: int, update: dict):
    """Update user data"""
    users.update_one({'user_id': user_id}, {'$set': update})

def is_premium(user_id: int) -> bool:
    """Check if user has active premium subscription"""
    return bool(premium_subscriptions.find_one({
        'user_id': user_id,
        'expires_at': {'$gt': datetime.utcnow()}
    }))

def get_premium_subscription(user_id: int):
    """Get premium subscription details for a user"""
    return premium_subscriptions.find_one({'user_id': user_id})

def add_premium_subscription(user_id: int, duration: str):
    """Add premium subscription with duration"""
    match = re.match(r'(\d+)\s*(day|month|year)s?', duration.lower())
    if not match:
        raise ValueError("Invalid duration format")
    
    quantity, unit = match.groups()
    quantity = int(quantity)
    
    # Calculate expiration
    created_at = datetime.utcnow()
    
    if unit == 'day':
        expires_at = created_at + timedelta(days=quantity)
    elif unit == 'month':
        expires_at = created_at + timedelta(days=quantity*30)
    elif unit == 'year':
        expires_at = created_at + timedelta(days=quantity*365)
    else:
        raise ValueError("Unsupported time unit")
    
    # Upsert subscription with creation time
    premium_subscriptions.update_one(
        {'user_id': user_id},
        {'$set': {
            'expires_at': expires_at,
            'created_at': created_at
        }},
        upsert=True
    )
    return expires_at

def get_bot_stats() -> dict:
    """Get bot statistics"""
    stats = {}
    
    stats['total_users'] = users.count_documents({})
    stats['active_premium'] = premium_subscriptions.count_documents({
        'expires_at': {'$gt': datetime.utcnow()}
    })
    
    # Active today (last 24 hours)
    now = time.time()
    stats['active_today'] = users.count_documents({
        'last_quiz_time': {'$gt': now - 86400}  # 86400 seconds = 24 hours
    })
    
    # Free quizzes generated
    total_quizzes = users.aggregate([
        {'$group': {'_id': None, 'total': {'$sum': '$quiz_count'}}}
    ])
    total_quiz_result = next(total_quizzes, None)
    stats['total_quiz_count'] = total_quiz_result['total'] if total_quiz_result else 0
    
    return stats
