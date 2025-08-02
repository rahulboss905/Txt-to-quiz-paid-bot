# Telegram Quiz Bot with Premium Features

![Bot Demo](https://img.shields.io/badge/Telegram-Quiz%20Bot-blue) 
![MongoDB](https://img.shields.io/badge/MongoDB-4.4%2B-green)

A feature-rich Telegram bot that converts text files into interactive quizzes with premium subscription capabilities.

## Features

- 🧠 Convert text files to timed quizzes
- ⏱️ 10-second interactive polls
- 💎 Premium subscriptions with duration-based access
- 📊 MongoDB storage for users and subscriptions
- 📈 Owner dashboard with statistics
- 🧾 Flexible question formatting
- 💻 Health check endpoint with status page

## Requirements

- Python 3.8+
- MongoDB 4.4+
- Telegram Bot API token
- Python packages: `python-telegram-bot`, `pymongo`

## Deployment

### 1. Environment Setup

Create `.env` file with required variables:

```env
TELEGRAM_TOKEN=your_bot_token_here
OWNER_ID=your_telegram_user_id
BOT_USERNAME=your_bot_username
MONGODB_URI=mongodb://user:password@host:port/database
PORT=8080  # Optional, for health checks

## Key Sections Explained

1. **Features**: Highlights bot capabilities
2. **Deployment**: Step-by-step setup instructions
3. **Commands**: User and owner command references
4. **File Format**: Quiz creation guidelines
5. **Premium Management**: Subscription workflows
6. **Health Checks**: Monitoring endpoints
7. **MongoDB Schema**: Database structure details

This README provides comprehensive setup and usage instructions for your quiz bot with MongoDB backend and premium subscription system.
