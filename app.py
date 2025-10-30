import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import logging
import base64
import io
import requests

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Config
BOT_TOKEN = '8295821417:AAEZytkScbqqajoK4kw2UyFHt96bKXYOa-A'
ADMIN_ID = '2098068100'
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'

# Storage
sessions = {}
messages = {}
files = {}

# Send Telegram message using requests
def send_telegram(chat_id, text, photo=None):
    try:
        if photo:
            url = f'{TELEGRAM_API}/sendPhoto'
            files_data = {'photo': ('photo.jpg', photo, 'image/jpeg')}
            data = {'chat_id': chat_id, 'caption': text}
            response = requests.post(url, data=data, files=files_data)
        else:
            url = f'{TELEGRAM_API}/sendMessage'
            data = {'chat_id': chat_id, 'text': text}
            response = requests.post(url, json=data)
        
        logger.info(f"Telegram response: {response.status_code}")
        return response.json()
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return None

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
    
    logger.info(f"New session: {sid}")
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
        
        # Send to Telegram
        user = sessions[sid]
        text = (
            f"💬 নতুন মেসেজ\n\n"
            f"🆔 Session: {sid}\n"
            f"👤 User: {user['name']}\n"
            f"📧 Email: {user.get('email', 'N/A')}\n"
            f"💭 Message: {msg}\n\n"
            f"📝 Reply করতে: {sid}: আপনার মেসেজ"
        )
        send_telegram(ADMIN_ID, text)
        
        logger.info(f"Message sent from {sid}")
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
        
        # Send to Telegram
        user = sessions[sid]
        text = (
            f"💬 নতুন মেসেজ (File)\n\n"
            f"🆔 Session: {sid}\n"
            f"👤 User: {user['name']}\n"
            f"📎 File: {file.filename}\n"
            f"💭 Message: {msg}\n\n"
            f"📝 Reply করতে: {sid}: আপনার মেসেজ"
        )
        
        if msg_type == 'image':
            send_telegram(ADMIN_ID, text, io.BytesIO(file_bytes))
        else:
            send_telegram(ADMIN_ID, text)
        
        logger.info(f"File uploaded from {sid}")
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

@app.route('/api/chat/webhook', methods=['POST'])
def webhook():
    """Telegram webhook for receiving replies"""
    try:
        data = request.json
        logger.info(f"Webhook received: {data}")
        
        if 'message' not in data:
            return jsonify({'ok': True})
        
        message = data['message']
        chat_id = str(message['chat']['id'])
        
        # Only process admin messages
        if chat_id != ADMIN_ID:
            return jsonify({'ok': True})
        
        # Handle text reply
        if 'text' in message:
            text = message['text']
            
            # Commands
            if text == '/start':
                send_telegram(ADMIN_ID, 
                    "✅ Bot Active!\n\n"
                    "📝 Text reply: SES_xxxxx: Message\n"
                    "📷 Photo: Send + caption SES_xxxxx\n"
                    "📄 File: Send + caption SES_xxxxx\n"
                    "📊 Sessions: /sessions"
                )
                return jsonify({'ok': True})
            
            if text == '/sessions':
                if not sessions:
                    send_telegram(ADMIN_ID, "📭 No active sessions")
                else:
                    msg = "📊 Active Sessions:\n\n"
                    for sid, data in sessions.items():
                        msg += f"🔹 {sid}\n   User: {data['name']}\n\n"
                    send_telegram(ADMIN_ID, msg)
                return jsonify({'ok': True})
            
            # Reply to session
            if ':' in text:
                sid, reply = text.split(':', 1)
                sid = sid.strip()
                reply = reply.strip()
                
                if sid in sessions:
                    messages[sid].append({
                        'from': 'admin',
                        'message': reply,
                        'type': 'text',
                        'timestamp': datetime.now().isoformat()
                    })
                    send_telegram(ADMIN_ID, f"✅ Reply sent to {sid}")
                else:
                    send_telegram(ADMIN_ID, f"❌ Session {sid} not found")
        
        # Handle photo reply
        elif 'photo' in message:
            caption = message.get('caption', '')
            if 'SES_' in caption:
                sid = caption.split(':')[0].strip() if ':' in caption else caption.strip()
                
                if sid in sessions:
                    # Get photo
                    photo = message['photo'][-1]
                    file_id = photo['file_id']
                    
                    # Download photo
                    file_info = requests.get(f'{TELEGRAM_API}/getFile?file_id={file_id}').json()
                    if file_info['ok']:
                        file_path = file_info['result']['file_path']
                        file_url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}'
                        photo_bytes = requests.get(file_url).content
                        
                        # Store photo
                        fid = str(uuid.uuid4())
                        files[fid] = {
                            'data': base64.b64encode(photo_bytes).decode(),
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
                        send_telegram(ADMIN_ID, f"✅ Photo sent to {sid}")
                else:
                    send_telegram(ADMIN_ID, f"❌ Session not found")
        
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'bot_token': BOT_TOKEN[:10] + '...'})

@app.route('/setup-webhook', methods=['GET'])
def setup_webhook():
    """Setup webhook - call this once after deploy"""
    webhook_url = request.host_url + 'api/chat/webhook'
    url = f'{TELEGRAM_API}/setWebhook?url={webhook_url}'
    response = requests.get(url)
    return jsonify(response.json())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
