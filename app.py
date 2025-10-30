import os
import asyncio
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from telegram import Update, Bot, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
import base64
import io

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8295821417:AAEZytkScbqqajoK4kw2UyFHt96bKXYOa-A')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', '2098068100')

# In-memory storage (use Redis/Database for production)
active_sessions = {}  # {session_id: {user_data}}
message_queue = {}  # {session_id: [messages]}
file_storage = {}  # {file_id: file_data}

# Initialize Telegram Bot
telegram_app = None
bot = None

async def init_telegram_bot():
    """Initialize Telegram bot"""
    global telegram_app, bot
    telegram_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    bot = telegram_app.bot
    
    # Add handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("sessions", list_sessions))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_reply))
    telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_admin_photo))
    telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_admin_document))
    
    # Start bot
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    logger.info("Telegram bot started successfully")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "✅ Live Chat Bot Active!\n\n"
        "🔹 Visitor message korle notification ashbe\n"
        "🔹 Text reply: SES_xxxxx: Tumhar message\n"
        "🔹 Photo/File reply: Photo/file pathao + caption e SES_xxxxx likho\n"
        "🔹 Active sessions: /sessions"
    )

async def list_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all active sessions"""
    if not active_sessions:
        await update.message.reply_text("📭 Kono active session nei")
        return
    
    message = "📊 Active Sessions:\n\n"
    for session_id, data in active_sessions.items():
        message += f"🔹 {session_id}\n"
        message += f"   Name: {data.get('name', 'Unknown')}\n"
        message += f"   Started: {data.get('started_at', 'Unknown')}\n"
        message += f"   Messages: {len(message_queue.get(session_id, []))}\n\n"
    
    await update.message.reply_text(message)

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin's text reply to customer"""
    text = update.message.text
    
    # Check if message contains session ID
    if ':' not in text:
        await update.message.reply_text(
            "⚠️ Format: SES_xxxxx: Tumhar message\n"
            "Example: SES_12345: Hello, how can I help?"
        )
        return
    
    session_id, reply_message = text.split(':', 1)
    session_id = session_id.strip()
    reply_message = reply_message.strip()
    
    if session_id not in active_sessions:
        await update.message.reply_text(f"❌ Session {session_id} khuje paoa jaini")
        return
    
    # Store admin reply
    if session_id not in message_queue:
        message_queue[session_id] = []
    
    message_queue[session_id].append({
        'from': 'admin',
        'message': reply_message,
        'type': 'text',
        'timestamp': datetime.now().isoformat()
    })
    
    await update.message.reply_text(f"✅ Reply sent to {session_id}")

async def handle_admin_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin's photo reply"""
    caption = update.message.caption or ""
    
    if ':' not in caption and 'SES_' not in caption:
        await update.message.reply_text(
            "⚠️ Caption e session ID dao\n"
            "Example: SES_12345"
        )
        return
    
    # Extract session ID
    session_id = caption.split(':')[0].strip() if ':' in caption else caption.strip()
    
    if session_id not in active_sessions:
        await update.message.reply_text(f"❌ Session {session_id} khuje paoa jaini")
        return
    
    # Get photo file
    photo = update.message.photo[-1]  # Get highest resolution
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    
    # Store file
    file_id = str(uuid.uuid4())
    file_storage[file_id] = {
        'data': base64.b64encode(file_bytes).decode('utf-8'),
        'mime_type': 'image/jpeg',
        'filename': f'photo_{file_id}.jpg'
    }
    
    # Store message
    if session_id not in message_queue:
        message_queue[session_id] = []
    
    message_queue[session_id].append({
        'from': 'admin',
        'message': caption.split(':', 1)[1].strip() if ':' in caption else '',
        'type': 'image',
        'file_id': file_id,
        'timestamp': datetime.now().isoformat()
    })
    
    await update.message.reply_text(f"✅ Photo sent to {session_id}")

async def handle_admin_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin's document reply"""
    caption = update.message.caption or ""
    
    if ':' not in caption and 'SES_' not in caption:
        await update.message.reply_text(
            "⚠️ Caption e session ID dao\n"
            "Example: SES_12345"
        )
        return
    
    # Extract session ID
    session_id = caption.split(':')[0].strip() if ':' in caption else caption.strip()
    
    if session_id not in active_sessions:
        await update.message.reply_text(f"❌ Session {session_id} khuje paoa jaini")
        return
    
    # Get document file
    document = update.message.document
    file = await document.get_file()
    file_bytes = await file.download_as_bytearray()
    
    # Store file
    file_id = str(uuid.uuid4())
    file_storage[file_id] = {
        'data': base64.b64encode(file_bytes).decode('utf-8'),
        'mime_type': document.mime_type,
        'filename': document.file_name
    }
    
    # Store message
    if session_id not in message_queue:
        message_queue[session_id] = []
    
    message_queue[session_id].append({
        'from': 'admin',
        'message': caption.split(':', 1)[1].strip() if ':' in caption else '',
        'type': 'file',
        'file_id': file_id,
        'filename': document.file_name,
        'timestamp': datetime.now().isoformat()
    })
    
    await update.message.reply_text(f"✅ File sent to {session_id}")

async def send_telegram_notification(session_id: str, message: str, user_info: dict, file_info=None):
    """Send notification to admin via Telegram"""
    notification = (
        f"💬 New Message from Website\n\n"
        f"🆔 Session: {session_id}\n"
        f"👤 User: {user_info.get('name', 'Anonymous')}\n"
        f"📧 Email: {user_info.get('email', 'N/A')}\n"
    )
    
    if file_info:
        notification += f"📎 File: {file_info.get('filename', 'attachment')}\n"
    
    if message:
        notification += f"💭 Message: {message}\n"
    
    notification += f"\n📝 Reply: {session_id}: Tumhar reply"
    
    try:
        if file_info:
            # Send file with notification
            file_data = base64.b64decode(file_info['data'])
            file_bytes = io.BytesIO(file_data)
            file_bytes.name = file_info['filename']
            
            if file_info['mime_type'].startswith('image/'):
                await bot.send_photo(
                    chat_id=ADMIN_CHAT_ID,
                    photo=file_bytes,
                    caption=notification
                )
            else:
                await bot.send_document(
                    chat_id=ADMIN_CHAT_ID,
                    document=file_bytes,
                    caption=notification
                )
        else:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=notification)
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")

# Flask API Routes

@app.route('/api/chat/init', methods=['POST'])
def init_chat():
    """Initialize a new chat session"""
    data = request.json
    session_id = f"SES_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    active_sessions[session_id] = {
        'name': data.get('name', 'Anonymous'),
        'email': data.get('email', ''),
        'started_at': datetime.now().isoformat()
    }
    
    message_queue[session_id] = []
    
    return jsonify({
        'success': True,
        'session_id': session_id
    })

@app.route('/api/chat/send', methods=['POST'])
def send_message():
    """Send text message from visitor"""
    data = request.json
    session_id = data.get('session_id')
    message = data.get('message')
    
    if not session_id or session_id not in active_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'}), 400
    
    # Store visitor message
    if session_id not in message_queue:
        message_queue[session_id] = []
    
    message_queue[session_id].append({
        'from': 'visitor',
        'message': message,
        'type': 'text',
        'timestamp': datetime.now().isoformat()
    })
    
    # Send notification to admin
    user_info = active_sessions[session_id]
    asyncio.create_task(send_telegram_notification(session_id, message, user_info))
    
    return jsonify({'success': True})

@app.route('/api/chat/upload', methods=['POST'])
def upload_file():
    """Upload file from visitor"""
    session_id = request.form.get('session_id')
    message = request.form.get('message', '')
    
    if not session_id or session_id not in active_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'}), 400
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file'}), 400
    
    file = request.files['file']
    
    # Read and store file
    file_bytes = file.read()
    file_id = str(uuid.uuid4())
    
    file_data = {
        'data': base64.b64encode(file_bytes).decode('utf-8'),
        'mime_type': file.content_type,
        'filename': file.filename
    }
    
    file_storage[file_id] = file_data
    
    # Store message
    if session_id not in message_queue:
        message_queue[session_id] = []
    
    msg_type = 'image' if file.content_type.startswith('image/') else 'file'
    
    message_queue[session_id].append({
        'from': 'visitor',
        'message': message,
        'type': msg_type,
        'file_id': file_id,
        'filename': file.filename,
        'timestamp': datetime.now().isoformat()
    })
    
    # Send notification to admin
    user_info = active_sessions[session_id]
    asyncio.create_task(send_telegram_notification(session_id, message, user_info, file_data))
    
    return jsonify({'success': True, 'file_id': file_id})

@app.route('/api/chat/file/<file_id>', methods=['GET'])
def get_file(file_id):
    """Get file by ID"""
    if file_id not in file_storage:
        return jsonify({'success': False, 'error': 'File not found'}), 404
    
    file_data = file_storage[file_id]
    file_bytes = base64.b64decode(file_data['data'])
    
    return send_file(
        io.BytesIO(file_bytes),
        mimetype=file_data['mime_type'],
        as_attachment=True,
        download_name=file_data['filename']
    )

@app.route('/api/chat/messages/<session_id>', methods=['GET'])
def get_messages(session_id):
    """Get all messages for a session"""
    if session_id not in active_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'}), 400
    
    messages = message_queue.get(session_id, [])
    
    return jsonify({
        'success': True,
        'messages': messages
    })

@app.route('/api/chat/poll/<session_id>', methods=['GET'])
def poll_messages(session_id):
    """Poll for new messages"""
    if session_id not in active_sessions:
        return jsonify({'success': False, 'error': 'Invalid session'}), 400
    
    last_message_count = int(request.args.get('last_count', 0))
    messages = message_queue.get(session_id, [])
    
    # Return only new messages
    new_messages = messages[last_message_count:]
    
    return jsonify({
        'success': True,
        'messages': new_messages,
        'total_count': len(messages)
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'bot_active': bot is not None})

if __name__ == '__main__':
    # Start Telegram bot in background
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(init_telegram_bot())
    
    import threading
    def run_async_loop():
        loop.run_forever()
    
    thread = threading.Thread(target=run_async_loop, daemon=True)
    thread.start()
    
    # Start Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
