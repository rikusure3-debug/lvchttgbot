import os
import uuid
import json
import base64
import io
from datetime import datetime, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import logging

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Config
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8295821417:AAEZytkScbqqajoK4kw2UyFHt96bKXYOa-A')
ADMIN_ID = os.environ.get('ADMIN_CHAT_ID', '2098068100')
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'

# Storage
sessions = {}
messages = {}
files = {}

# Session cleanup
def cleanup_old_sessions():
    try:
        cutoff = datetime.now() - timedelta(hours=24)
        to_remove = []
        for sid, data in sessions.items():
            started = datetime.fromisoformat(data['started'])
            if started < cutoff:
                to_remove.append(sid)
        
        for sid in to_remove:
            if sid in sessions:
                del sessions[sid]
            if sid in messages:
                del messages[sid]
            logger.info(f"Cleaned up old session: {sid}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

def telegram_request(method, data=None, files_data=None):
    """Make Telegram API request"""
    try:
        url = f'{TELEGRAM_API}/{method}'
        
        if files_data:
            # Multipart form data for file uploads
            import mimetypes
            boundary = '----WebKitFormBoundary' + str(uuid.uuid4()).replace('-', '')
            body = []
            
            # Add text fields
            if data:
                for key, value in data.items():
                    body.append(f'--{boundary}'.encode())
                    body.append(f'Content-Disposition: form-data; name="{key}"'.encode())
                    body.append(b'')
                    body.append(str(value).encode())
            
            # Add file
            for field_name, (filename, file_data, mime_type) in files_data.items():
                body.append(f'--{boundary}'.encode())
                body.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode())
                body.append(f'Content-Type: {mime_type}'.encode())
                body.append(b'')
                body.append(file_data)
            
            body.append(f'--{boundary}--'.encode())
            body = b'\r\n'.join(body)
            
            req = Request(url, data=body, headers={
                'Content-Type': f'multipart/form-data; boundary={boundary}'
            })
        elif data:
            data_encoded = json.dumps(data).encode('utf-8')
            req = Request(url, data=data_encoded, headers={'Content-Type': 'application/json'})
        else:
            req = Request(url)
        
        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result
    except Exception as e:
        logger.error(f"Telegram {method} error: {e}")
        return None

def send_message(chat_id, text):
    """Send text message"""
    return telegram_request('sendMessage', {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    })

def send_photo(chat_id, photo_data, caption=''):
    """Send photo to Telegram"""
    return telegram_request('sendPhoto', 
        data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'},
        files_data={'photo': ('photo.jpg', photo_data, 'image/jpeg')}
    )

def send_document(chat_id, document_data, filename, mime_type, caption=''):
    """Send document to Telegram"""
    return telegram_request('sendDocument',
        data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'},
        files_data={'document': (filename, document_data, mime_type)}
    )

def send_audio(chat_id, audio_data, filename, caption=''):
    """Send audio/voice to Telegram"""
    return telegram_request('sendVoice',
        data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'},
        files_data={'voice': (filename, audio_data, 'audio/ogg')}
    )

def download_telegram_file(file_id):
    """Download file from Telegram"""
    try:
        # Get file path
        result = telegram_request('getFile', {'file_id': file_id})
        if not result or not result.get('ok'):
            return None
        
        file_path = result['result']['file_path']
        file_url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}'
        
        # Download file
        with urlopen(file_url, timeout=30) as response:
            return response.read()
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

# Routes
@app.route('/api/chat/init', methods=['POST'])
def init_chat():
    data = request.json
    sid = f"SES_{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
    
    sessions[sid] = {
        'name': data.get('name', 'Anonymous'),
        'email': data.get('email', ''),
        'started': datetime.now().isoformat(),
        'last_active': datetime.now().isoformat(),
        'initial_page': data.get('page_url', 'Unknown'),
        'initial_page_title': data.get('page_title', 'Unknown')
    }
    messages[sid] = []
    
    import threading
    threading.Thread(target=cleanup_old_sessions, daemon=True).start()
    
    # Send notification to admin
    page_info = sessions[sid]['initial_page_title']
    page_url = sessions[sid]['initial_page']
    notification = (
        f"🆕 <b>নতুন Chat Session শুরু হয়েছে!</b>\n\n"
        f"👤 <b>Name:</b> {sessions[sid]['name']}\n"
        f"📧 <b>Email:</b> {sessions[sid].get('email', 'N/A')}\n"
        f"📄 <b>Page:</b> {page_info}\n"
        f"🔗 <b>URL:</b> {page_url}\n\n"
        f"📋 <b>Session ID:</b> <code>{sid}</code>\n"
        f"⏰ <b>Time:</b> {datetime.now().strftime('%I:%M %p')}"
    )
    threading.Thread(target=send_message, args=(ADMIN_ID, notification), daemon=True).start()
    
    logger.info(f"New session: {sid} - {sessions[sid]['name']} from {page_info}")
    
    return jsonify({
        'success': True,
        'session_id': sid,
        'message': 'Session created'
    })

@app.route('/api/chat/send', methods=['POST'])
def send_msg():
    try:
        data = request.json
        sid = data.get('session_id')
        msg = data.get('message', '')
        page_url = data.get('page_url', 'Unknown')
        page_title = data.get('page_title', 'Unknown')
        
        if not sid or sid not in sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 400
        
        messages[sid].append({
            'from': 'visitor',
            'message': msg,
            'type': 'text',
            'timestamp': datetime.now().isoformat(),
            'page_url': page_url,
            'page_title': page_title
        })
        
        user = sessions[sid]
        text = (
            f"💬 <b>নতুন মেসেজ</b>\n\n"
            f"👤 <b>User:</b> {user['name']}\n"
            f"📧 <b>Email:</b> {user.get('email', 'N/A')}\n"
            f"📄 <b>Current Page:</b> {page_title}\n"
            f"🔗 <b>URL:</b> {page_url}\n\n"
            f"💭 <b>Message:</b> {msg}\n\n"
            f"📋 <b>Session:</b> <code>{sid}</code>\n\n"
            f"📝 Reply: <code>{sid}: Your message</code>"
        )
        
        from threading import Thread
        Thread(target=send_message, args=(ADMIN_ID, text), daemon=True).start()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Send error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/upload', methods=['POST'])
def upload():
    try:
        sid = request.form.get('session_id')
        msg = request.form.get('message', '')
        page_url = request.form.get('page_url', 'Unknown')
        page_title = request.form.get('page_title', 'Unknown')
        
        if not sid or sid not in sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 400
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file'}), 400
        
        file = request.files['file']
        file_bytes = file.read()
        fid = str(uuid.uuid4())
        
        mime_type = file.content_type or 'application/octet-stream'
        filename = file.filename or 'file'
        
        file_data = {
            'data': base64.b64encode(file_bytes).decode(),
            'mime': mime_type,
            'name': filename
        }
        files[fid] = file_data
        
        # Detect if it's voice message
        is_voice = 'voice-message' in filename.lower() or mime_type.startswith('audio/')
        
        if is_voice:
            msg_type = 'voice'
        elif mime_type.startswith('image/'):
            msg_type = 'image'
        else:
            msg_type = 'file'
        
        messages[sid].append({
            'from': 'visitor',
            'message': msg,
            'type': msg_type,
            'file_id': fid,
            'filename': filename,
            'timestamp': datetime.now().isoformat(),
            'page_url': page_url,
            'page_title': page_title
        })
        
        # Send to admin with actual file
        user = sessions[sid]
        caption = (
            f"💬 <b>নতুন মেসেজ</b>\n\n"
            f"👤 {user['name']}\n"
            f"📧 {user.get('email', 'N/A')}\n"
            f"📄 <b>Page:</b> {page_title}\n"
            f"🔗 {page_url}\n\n"
            f"💭 {msg if msg else '(No message)'}\n\n"
            f"📋 <code>{sid}</code>\n\n"
            f"Reply: <code>{sid}: Your message</code>"
        )
        
        def send_file_to_admin():
            try:
                if is_voice:
                    # Convert webm to ogg if needed
                    send_audio(ADMIN_ID, file_bytes, filename, caption)
                elif mime_type.startswith('image/'):
                    send_photo(ADMIN_ID, file_bytes, caption)
                else:
                    send_document(ADMIN_ID, file_bytes, filename, mime_type, caption)
            except Exception as e:
                logger.error(f"Send file to admin error: {e}")
                # Fallback to text notification
                send_message(ADMIN_ID, caption + f"\n\n⚠️ File: {filename}")
        
        from threading import Thread
        Thread(target=send_file_to_admin, daemon=True).start()
        
        logger.info(f"File uploaded: {sid} - {filename} ({msg_type})")
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


@app.route('/api/chat/verify/<session_id>', methods=['GET'])
def verify_session(session_id):
    """Verify if a session exists and is still valid"""
    try:
        if session_id not in sessions:
            return jsonify({'success': False, 'error': 'Session not found'}), 404
        
        # Check if session is too old (more than 24 hours)
        session_data = sessions[session_id]
        started = datetime.fromisoformat(session_data['started'])
        age = datetime.now() - started
        
        if age.total_seconds() > 86400:  # 24 hours
            return jsonify({'success': False, 'error': 'Session expired'}), 404
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'name': session_data.get('name'),
            'age_hours': round(age.total_seconds() / 3600, 1)
        })
    except Exception as e:
        logger.error(f"Verify error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/poll/<sid>', methods=['GET'])
def poll(sid):
    if sid in sessions:
        sessions[sid]['last_active'] = datetime.now().isoformat()
    else:
        logger.warning(f"Poll for non-existent session: {sid}")
        return jsonify({
            'success': False,
            'error': 'Session not found or expired',
            'session_id': sid
        }), 404
    
    last_count = int(request.args.get('last_count', 0))
    all_msgs = messages.get(sid, [])
    new_msgs = all_msgs[last_count:]
    
    return jsonify({
        'success': True,
        'messages': new_msgs,
        'total_count': len(all_msgs)
    })

@app.route('/api/chat/webhook', methods=['POST'])
def webhook():
    try:
        update = request.json
        logger.info(f"Webhook received: {json.dumps(update)[:200]}")
        
        if 'message' not in update:
            return jsonify({'ok': True})
        
        msg = update['message']
        chat_id = str(msg['chat']['id'])
        
        # Only process messages from admin
        if chat_id != ADMIN_ID:
            logger.info(f"Ignoring message from non-admin: {chat_id}")
            return jsonify({'ok': True})
        
        # Handle text messages (replies)
        if 'text' in msg:
            text = msg['text'].strip()
            
            # /start command
            if text == '/start':
                welcome = (
                    "✅ <b>Live Chat Bot Active!</b>\n\n"
                    "🔹 Visitor থেকে message আসলে notification পাবেন\n"
                    "🔹 Text reply: <code>SES_xxxxx: Your message</code>\n"
                    "🔹 Photo/File reply: Photo/file পাঠান + caption এ <code>SES_xxxxx</code> লিখুন\n"
                    "🔹 Voice reply: Voice message পাঠান + caption এ <code>SES_xxxxx</code>\n\n"
                    "<b>Commands:</b>\n"
                    "/sessions - Active sessions দেখুন\n"
                    "/close SES_xxxxx - Session বন্ধ করুন\n"
                    "/broadcast message - সবাইকে message পাঠান"
                )
                send_message(ADMIN_ID, welcome)
                return jsonify({'ok': True})
            
            # /sessions command
            if text == '/sessions':
                if not sessions:
                    send_message(ADMIN_ID, "📭 <b>No active sessions</b>")
                else:
                    msg_text = f"📊 <b>Active Sessions: {len(sessions)}</b>\n\n"
                    for sid, data in list(sessions.items())[:10]:  # Show max 10
                        started = datetime.fromisoformat(data['started'])
                        duration = datetime.now() - started
                        hours = duration.seconds // 3600
                        minutes = (duration.seconds % 3600) // 60
                        
                        msg_text += (
                            f"🆔 <code>{sid}</code>\n"
                            f"👤 {data['name']}\n"
                            f"⏱️ {hours}h {minutes}m\n"
                            f"💬 {len(messages.get(sid, []))} messages\n\n"
                        )
                    
                    if len(sessions) > 10:
                        msg_text += f"\n<i>... and {len(sessions) - 10} more</i>"
                    
                    send_message(ADMIN_ID, msg_text)
                return jsonify({'ok': True})
            
            # /close command
            if text.startswith('/close '):
                sid = text.replace('/close ', '').strip()
                
                if sid not in sessions:
                    send_message(ADMIN_ID, f"❌ Session not found: <code>{sid}</code>")
                else:
                    user_name = sessions[sid]['name']
                    
                    if sid in messages:
                        messages[sid].append({
                            'from': 'admin',
                            'message': '⚠️ এই চ্যাট সেশন বন্ধ করা হয়েছে। নতুন চ্যাট শুরু করতে পেজ রিফ্রেশ করুন।',
                            'type': 'text',
                            'timestamp': datetime.now().isoformat()
                        })
                    
                    del sessions[sid]
                    send_message(ADMIN_ID, f"✅ Session closed: <code>{sid}</code>\n👤 User: {user_name}")
                return jsonify({'ok': True})
            
            # /broadcast command
            if text.startswith('/broadcast '):
                broadcast_msg = text.replace('/broadcast ', '').strip()
                
                if not broadcast_msg:
                    send_message(ADMIN_ID, "⚠️ Usage: <code>/broadcast Your message</code>")
                    return jsonify({'ok': True})
                
                if not sessions:
                    send_message(ADMIN_ID, "📭 No active sessions")
                    return jsonify({'ok': True})
                
                sent_count = 0
                for sid in list(sessions.keys()):
                    if sid in messages:
                        messages[sid].append({
                            'from': 'admin',
                            'message': f"📢 <b>Announcement:</b> {broadcast_msg}",
                            'type': 'text',
                            'timestamp': datetime.now().isoformat()
                        })
                        sent_count += 1
                
                send_message(ADMIN_ID, f"📢 Broadcast sent to {sent_count} session(s)")
                return jsonify({'ok': True})
            
            # Reply to visitor
            if ':' in text and 'SES_' in text:
                parts = text.split(':', 1)
                sid = parts[0].strip()
                reply = parts[1].strip() if len(parts) > 1 else ''
                
                if sid in sessions:
                    messages[sid].append({
                        'from': 'admin',
                        'message': reply,
                        'type': 'text',
                        'timestamp': datetime.now().isoformat()
                    })
                    send_message(ADMIN_ID, f"✅ Reply sent to: <code>{sid}</code>")
                    logger.info(f"Reply added to {sid}")
                else:
                    send_message(ADMIN_ID, f"❌ Session not found: <code>{sid}</code>")
        
        # Handle photo messages from admin
        elif 'photo' in msg:
            caption = msg.get('caption', '').strip()
            
            if 'SES_' not in caption:
                send_message(ADMIN_ID, "⚠️ Caption এ session ID দিন\nExample: <code>SES_xxxxx</code>")
                return jsonify({'ok': True})
            
            # Extract session ID
            sid = caption.split(':')[0].strip() if ':' in caption else caption.split()[0].strip()
            message_text = caption.split(':', 1)[1].strip() if ':' in caption else ''
            
            if sid not in sessions:
                send_message(ADMIN_ID, f"❌ Session not found: <code>{sid}</code>")
                return jsonify({'ok': True})
            
            # Download photo
            photo = msg['photo'][-1]  # Highest resolution
            file_id = photo['file_id']
            photo_data = download_telegram_file(file_id)
            
            if not photo_data:
                send_message(ADMIN_ID, "❌ Failed to download photo")
                return jsonify({'ok': True})
            
            # Store file
            fid = str(uuid.uuid4())
            files[fid] = {
                'data': base64.b64encode(photo_data).decode(),
                'mime': 'image/jpeg',
                'name': f'photo_{fid}.jpg'
            }
            
            # Add to messages
            messages[sid].append({
                'from': 'admin',
                'message': message_text,
                'type': 'image',
                'file_id': fid,
                'filename': f'photo_{fid}.jpg',
                'timestamp': datetime.now().isoformat()
            })
            
            send_message(ADMIN_ID, f"✅ Photo sent to: <code>{sid}</code>")
            logger.info(f"Photo sent to {sid}")
        
        # Handle document/file messages from admin
        elif 'document' in msg:
            caption = msg.get('caption', '').strip()
            
            if 'SES_' not in caption:
                send_message(ADMIN_ID, "⚠️ Caption এ session ID দিন\nExample: <code>SES_xxxxx</code>")
                return jsonify({'ok': True})
            
            sid = caption.split(':')[0].strip() if ':' in caption else caption.split()[0].strip()
            message_text = caption.split(':', 1)[1].strip() if ':' in caption else ''
            
            if sid not in sessions:
                send_message(ADMIN_ID, f"❌ Session not found: <code>{sid}</code>")
                return jsonify({'ok': True})
            
            # Download document
            document = msg['document']
            file_id = document['file_id']
            file_data = download_telegram_file(file_id)
            
            if not file_data:
                send_message(ADMIN_ID, "❌ Failed to download file")
                return jsonify({'ok': True})
            
            # Store file
            fid = str(uuid.uuid4())
            filename = document.get('file_name', f'file_{fid}')
            mime_type = document.get('mime_type', 'application/octet-stream')
            
            files[fid] = {
                'data': base64.b64encode(file_data).decode(),
                'mime': mime_type,
                'name': filename
            }
            
            # Add to messages
            messages[sid].append({
                'from': 'admin',
                'message': message_text,
                'type': 'file',
                'file_id': fid,
                'filename': filename,
                'timestamp': datetime.now().isoformat()
            })
            
            send_message(ADMIN_ID, f"✅ File sent to: <code>{sid}</code>")
            logger.info(f"File sent to {sid}")
        
        # Handle voice messages from admin
        elif 'voice' in msg:
            caption = msg.get('caption', '').strip()
            
            if 'SES_' not in caption:
                send_message(ADMIN_ID, "⚠️ Caption এ session ID দিন\nExample: <code>SES_xxxxx</code>")
                return jsonify({'ok': True})
            
            sid = caption.split(':')[0].strip() if ':' in caption else caption.split()[0].strip()
            message_text = caption.split(':', 1)[1].strip() if ':' in caption else ''
            
            if sid not in sessions:
                send_message(ADMIN_ID, f"❌ Session not found: <code>{sid}</code>")
                return jsonify({'ok': True})
            
            # Download voice
            voice = msg['voice']
            file_id = voice['file_id']
            voice_data = download_telegram_file(file_id)
            
            if not voice_data:
                send_message(ADMIN_ID, "❌ Failed to download voice")
                return jsonify({'ok': True})
            
            # Store file
            fid = str(uuid.uuid4())
            filename = f'voice_{fid}.ogg'
            
            files[fid] = {
                'data': base64.b64encode(voice_data).decode(),
                'mime': 'audio/ogg',
                'name': filename
            }
            
            # Add to messages
            messages[sid].append({
                'from': 'admin',
                'message': message_text if message_text else '🎤 Voice message',
                'type': 'voice',
                'file_id': fid,
                'filename': filename,
                'timestamp': datetime.now().isoformat()
            })
            
            send_message(ADMIN_ID, f"✅ Voice sent to: <code>{sid}</code>")
            logger.info(f"Voice sent to {sid}")
        
        # Handle audio messages from admin
        elif 'audio' in msg:
            caption = msg.get('caption', '').strip()
            
            if 'SES_' not in caption:
                send_message(ADMIN_ID, "⚠️ Caption এ session ID দিন")
                return jsonify({'ok': True})
            
            sid = caption.split(':')[0].strip() if ':' in caption else caption.split()[0].strip()
            message_text = caption.split(':', 1)[1].strip() if ':' in caption else ''
            
            if sid not in sessions:
                send_message(ADMIN_ID, f"❌ Session not found: <code>{sid}</code>")
                return jsonify({'ok': True})
            
            # Download audio
            audio = msg['audio']
            file_id = audio['file_id']
            audio_data = download_telegram_file(file_id)
            
            if not audio_data:
                send_message(ADMIN_ID, "❌ Failed to download audio")
                return jsonify({'ok': True})
            
            # Store file
            fid = str(uuid.uuid4())
            filename = audio.get('file_name', f'audio_{fid}.mp3')
            mime_type = audio.get('mime_type', 'audio/mpeg')
            
            files[fid] = {
                'data': base64.b64encode(audio_data).decode(),
                'mime': mime_type,
                'name': filename
            }
            
            # Add to messages
            messages[sid].append({
                'from': 'admin',
                'message': message_text if message_text else '🎵 Audio message',
                'type': 'voice',
                'file_id': fid,
                'filename': filename,
                'timestamp': datetime.now().isoformat()
            })
            
            send_message(ADMIN_ID, f"✅ Audio sent to: <code>{sid}</code>")
            logger.info(f"Audio sent to {sid}")
        
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({'ok': True})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'active_sessions': len(sessions),
        'total_messages': sum(len(m) for m in messages.values()),
        'session_ids': list(sessions.keys()) if len(sessions) < 10 else f"{len(sessions)} active"
    })

@app.route('/test-bot', methods=['GET'])
def test_bot():
    try:
        result = telegram_request('getMe')
        return jsonify({
            'success': result.get('ok', False) if result else False,
            'bot_info': result.get('result', {}) if result else {},
            'message': 'Bot working!' if result and result.get('ok') else 'Bot token invalid'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/setup-webhook', methods=['GET'])
def setup_webhook():
    try:
        host = request.host
        webhook_url = f'https://{host}/api/chat/webhook'
        
        # Delete existing webhook
        telegram_request('deleteWebhook')
        
        # Set new webhook
        result = telegram_request('setWebhook', {'url': webhook_url})
        
        return jsonify({
            'success': result.get('ok', False) if result else False,
            'webhook_url': webhook_url,
            'result': result
        })
    except Exception as e:
        logger.error(f"Webhook setup error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/webhook-info', methods=['GET'])
def webhook_info():
    try:
        result = telegram_request('getWebhookInfo')
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug/session/<sid>', methods=['GET'])
def debug_session(sid):
    return jsonify({
        'session_exists': sid in sessions,
        'session_data': sessions.get(sid, {}),
        'message_count': len(messages.get(sid, [])),
        'messages': messages.get(sid, [])[-5:],  # Last 5 messages
        'all_sessions': list(sessions.keys())
    })

@app.route('/')
def index():
    return jsonify({
        'service': 'Live Chat API with Image & Voice Support',
        'status': 'running',
        'features': [
            '✅ Text messages',
            '✅ Image upload & display',
            '✅ File upload & download',
            '✅ Voice messages (both ways)',
            '✅ Admin replies via Telegram',
            '✅ Real-time polling'
        ],
        'setup': [
            '1. /test-bot - Verify bot',
            '2. /setup-webhook - Enable Telegram webhook',
            '3. Send /start to bot in Telegram',
            '4. Test by sending message from website'
        ]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting on port {port}")
    logger.info(f"Bot: {BOT_TOKEN[:20]}...")
    logger.info(f"Admin: {ADMIN_ID}")
    app.run(host='0.0.0.0', port=port, threaded=True)
