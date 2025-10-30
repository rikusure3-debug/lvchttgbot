import os
import asyncio
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from telegram import Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import logging
import base64
import io
from threading import Thread

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Config
BOT_TOKEN = '8295821417:AAEZytkScbqqajoK4kw2UyFHt96bKXYOa-A'
ADMIN_ID = '2098068100'

# Storage
sessions = {}
messages = {}
files = {}

# Bot
bot = None
telegram_app = None

# Initialize bot
def init_bot():
    global bot, telegram_app
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def setup():
        global bot, telegram_app
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        bot = telegram_app.bot
        
        # Commands
        async def start(update, context):
            await update.message.reply_text(
                "✅ Bot Active!\n\n"
                "📝 Text reply: SES_xxxxx: Message\n"
                "📷 Photo: Send photo + caption SES_xxxxx\n"
                "📄 File: Send file + caption SES_xxxxx\n"
                "📊 Sessions: /sessions"
            )
        
        async def list_sessions(update, context):
            if not sessions:
                await update.message.reply_text("📭 No active sessions")
                return
            msg = "📊 Active Sessions:\n\n"
            for sid, data in sessions.items():
                msg += f"🔹 {sid}\n   User: {data['name']}\n\n"
            await update.message.reply_text(msg)
        
        async def handle_text(update, context):
            text = update.message.text
            if ':' not in text:
                await update.message.reply_text("⚠️ Format: SES_xxxxx: Your message")
                return
            
            sid, msg = text.split(':', 1)
            sid = sid.strip()
            msg = msg.strip()
            
            if sid not in sessions:
                await update.message.reply_text(f"❌ Session {sid} not found")
                return
            
            messages[sid].append({
                'from': 'admin',
                'message': msg,
                'type': 'text',
                'timestamp': datetime.now().isoformat()
            })
            await update.message.reply_text(f"✅ Sent to {sid}")
        
        async def handle_photo(update, context):
            caption = update.message.caption or ""
            if 'SES_' not in caption:
                await update.message.reply_text("⚠️ Caption e session ID dao")
                return
            
            sid = caption.split(':')[0].strip() if ':' in caption else caption.strip()
            
            if sid not in sessions:
                await update.message.reply_text(f"❌ Session not found")
                return
            
            photo = update.message.photo[-1]
            file = await photo.get_file()
            file_bytes = await file.download_as_bytearray()
            
            fid = str(uuid.uuid4())
            files[fid] = {
                'data': base64.b64encode(file_bytes).decode(),
                'mime': 'image/jpeg',
                'name': f'photo_{fid}.jpg'
            }
            
            messages[sid].append({
                'from': 'admin',
                'message': caption.split(':', 1)[1].strip() if ':' in caption else '',
                'type': 'image',
                'file_id': fid,
                'timestamp': datetime.now().isoformat()
            })
            await update.message.reply_text(f"✅ Photo sent to {sid}")
        
        async def handle_doc(update, context):
            caption = update.message.caption or ""
            if 'SES_' not in caption:
                await update.message.reply_text("⚠️ Caption e session ID dao")
                return
            
            sid = caption.split(':')[0].strip() if ':' in caption else caption.strip()
            
            if sid not in sessions:
                await update.message.reply_text(f"❌ Session not found")
                return
            
            doc = update.message.document
            file = await doc.get_file()
            file_bytes = await file.download_as_bytearray()
            
            fid = str(uuid.uuid4())
            files[fid] = {
                'data': base64.b64encode(file_bytes).decode(),
                'mime': doc.mime_type,
                'name': doc.file_name
            }
            
            messages[sid].append({
                'from': 'admin',
                'message': caption.split(':', 1)[1].strip() if ':' in caption else '',
                'type': 'file',
                'file_id': fid,
                'filename': doc.file_name,
                'timestamp': datetime.now().isoformat()
            })
            await update.message.reply_text(f"✅ File sent to {sid}")
        
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("sessions", list_sessions))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
        
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        logger.info("✅ Bot started")
    
    loop.run_until_complete(setup())
    loop.run_forever()

# Send notification
def notify_admin(sid, msg, user, file_data=None):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def send():
            text = (
                f"💬 New Message\n\n"
                f"🆔 {sid}\n"
                f"👤 {user.get('name', 'Anonymous')}\n"
                f"📧 {user.get('email', 'N/A')}\n"
            )
            
            if file_data:
                text += f"📎 {file_data.get('name', 'file')}\n"
            if msg:
                text += f"💭 {msg}\n"
            
            text += f"\n📝 Reply: {sid}: Your message"
            
            if file_data:
                file_bytes = io.BytesIO(base64.b64decode(file_data['data']))
                file_bytes.name = file_data['name']
                
                if file_data['mime'].startswith('image/'):
                    await bot.send_photo(chat_id=ADMIN_ID, photo=file_bytes, caption=text)
                else:
                    await bot.send_document(chat_id=ADMIN_ID, document=file_bytes, caption=text)
            else:
                await bot.send_message(chat_id=ADMIN_ID, text=text)
        
        loop.run_until_complete(send())
        loop.close()
    except Exception as e:
        logger.error(f"Notification error: {e}")

# Routes
@app.route('/api/chat/init', methods=['POST'])
def init_chat():
    data = request.json
    sid = f"SES_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    sessions[sid] = {
        'name': data.get('name', 'Anonymous'),
        'email': data.get('email', ''),
        'started': datetime.now().isoformat()
    }
    messages[sid] = []
    
    return jsonify({'success': True, 'session_id': sid})

@app.route('/api/chat/send', methods=['POST'])
def send_msg():
    try:
        data = request.json
        sid = data.get('session_id')
        msg = data.get('message')
        
        if sid not in sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 400
        
        messages[sid].append({
            'from': 'visitor',
            'message': msg,
            'type': 'text',
            'timestamp': datetime.now().isoformat()
        })
        
        # Notify in background
        Thread(target=notify_admin, args=(sid, msg, sessions[sid])).start()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Send error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/upload', methods=['POST'])
def upload():
    try:
        sid = request.form.get('session_id')
        msg = request.form.get('message', '')
        
        if sid not in sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 400
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file'}), 400
        
        file = request.files['file']
        file_bytes = file.read()
        fid = str(uuid.uuid4())
        
        file_data = {
            'data': base64.b64encode(file_bytes).decode(),
            'mime': file.content_type,
            'name': file.filename
        }
        files[fid] = file_data
        
        msg_type = 'image' if file.content_type.startswith('image/') else 'file'
        
        messages[sid].append({
            'from': 'visitor',
            'message': msg,
            'type': msg_type,
            'file_id': fid,
            'filename': file.filename,
            'timestamp': datetime.now().isoformat()
        })
        
        # Notify in background
        Thread(target=notify_admin, args=(sid, msg, sessions[sid], file_data)).start()
        
        return jsonify({'success': True, 'file_id': fid})
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/file/<fid>', methods=['GET'])
def get_file(fid):
    if fid not in files:
        return jsonify({'error': 'Not found'}), 404
    
    file_data = files[fid]
    file_bytes = base64.b64decode(file_data['data'])
    
    return send_file(
        io.BytesIO(file_bytes),
        mimetype=file_data['mime'],
        as_attachment=True,
        download_name=file_data['name']
    )

@app.route('/api/chat/poll/<sid>', methods=['GET'])
def poll(sid):
    if sid not in sessions:
        return jsonify({'success': False}), 400
    
    last = int(request.args.get('last_count', 0))
    msgs = messages.get(sid, [])
    
    return jsonify({
        'success': True,
        'messages': msgs[last:],
        'total_count': len(msgs)
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'bot': bot is not None})

if __name__ == '__main__':
    # Start bot in background
    bot_thread = Thread(target=init_bot, daemon=True)
    bot_thread.start()
    
    # Wait for bot
    import time
    time.sleep(3)
    
    # Start Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
