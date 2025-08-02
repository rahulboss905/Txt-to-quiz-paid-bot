import os
import logging
import re
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

# [Keep all other existing database functions unchanged]
