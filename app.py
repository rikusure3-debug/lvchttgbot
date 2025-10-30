import os
import uuid
import json
import base64
import io
from datetime import datetime
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
BOT_TOKEN = '8295821417:AAEZytkScbqqajoK4kw2UyFHt96bKXYOa-A'
ADMIN_ID = '2098068100'
TELEGRAM_API = f'https://api.telegram.org/bot{BOT_TOKEN}'

# Storage
sessions = {}
messages = {}
files = {}

def telegram_request(method, data=None):
    """Make Telegram API request using urllib"""
    try:
        url = f'{TELEGRAM_API}/{method}'
        
        if data:
            data_encoded = json.dumps(data).encode('utf-8')
            req = Request(url, data=data_encoded, headers={'Content-Type': 'application/json'})
        else:
            req = Request(url)
        
        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            logger.info(f"Telegram {method}: {result.get('ok', False)}")
            return result
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return None

def send_message(chat_id, text):
    """Send text message to Telegram"""
    return telegram_request('sendMessage', {
        'chat_id': chat_id,
        'text': text
    })

# Routes
@app.route('/api/chat/init', methods=['POST'])
def init_chat():
    data = request.json
    sid = f"SES_{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
    
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
        msg = data.get('message', '')
        
        if not sid or sid not in sessions:
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
            f"🆔 {sid}\n"
            f"👤 {user['name']}\n"
            f"📧 {user.get('email', 'N/A')}\n"
            f"💭 {msg}\n\n"
            f"📝 Reply: {sid}: আপনার মেসেজ"
        )
        
        # Send in background thread
        from threading import Thread
        Thread(target=send_message, args=(ADMIN_ID, text), daemon=True).start()
        
        logger.info(f"Message from {sid}")
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Send error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/upload', methods=['POST'])
def upload():
    try:
        sid = request.form.get('session_id')
        msg = request.form.get('message', '')
        
        if not sid or sid not in sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 400
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file'}), 400
        
        file = request.files['file']
        file_bytes = file.read()
        fid = str(uuid.uuid4())
        
        file_data = {
            'data': base64.b64encode(file_bytes).decode(),
            'mime': file.content_type or 'application/octet-stream',
            'name': file.filename or 'file'
        }
        files[fid] = file_data
        
        msg_type = 'image' if (file.content_type and file.content_type.startswith('image/')) else 'file'
        
        messages[sid].append({
            'from': 'visitor',
            'message': msg,
            'type': msg_type,
            'file_id': fid,
            'filename': file.filename,
            'timestamp': datetime.now().isoformat()
        })
        
        # Notify admin
        user = sessions[sid]
        text = (
            f"💬 নতুন মেসেজ (File)\n\n"
            f"🆔 {sid}\n"
            f"👤 {user['name']}\n"
            f"📎 {file.filename}\n"
            f"💭 {msg}\n\n"
            f"📝 Reply: {sid}: আপনার মেসেজ"
        )
        
        from threading import Thread
        Thread(target=send_message, args=(ADMIN_ID, text), daemon=True).start()
        
        logger.info(f"File from {sid}")
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
        return jsonify({'success': False, 'error': 'Invalid session'}), 400
    
    last = int(request.args.get('last_count', 0))
    msgs = messages.get(sid, [])
    
    return jsonify({
        'success': True,
        'messages': msgs[last:],
        'total_count': len(msgs)
    })

@app.route('/api/chat/reply', methods=['POST'])
def manual_reply():
    """Manual reply endpoint for admin"""
    try:
        data = request.json
        sid = data.get('session_id')
        reply = data.get('message')
        
        if not sid or sid not in sessions:
            return jsonify({'success': False, 'error': 'Invalid session'}), 400
        
        messages[sid].append({
            'from': 'admin',
            'message': reply,
            'type': 'text',
            'timestamp': datetime.now().isoformat()
        })
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/webhook', methods=['POST'])
def webhook():
    """Telegram webhook for receiving admin replies"""
    try:
        data = request.json
        logger.info(f"Webhook: {json.dumps(data)[:200]}")
        
        if 'message' not in data:
            return jsonify({'ok': True})
        
        message = data['message']
        chat_id = str(message['chat']['id'])
        
        # Only admin
        if chat_id != ADMIN_ID:
            return jsonify({'ok': True})
        
        # Handle commands
        if 'text' in message:
            text = message['text']
            
            if text == '/start':
                send_message(ADMIN_ID, 
                    "✅ Bot Active!\n\n"
                    "📝 Reply: SES_xxxxx: Message\n"
                    "📊 Sessions: /sessions"
                )
                return jsonify({'ok': True})
            
            if text == '/sessions':
                if not sessions:
                    send_message(ADMIN_ID, "📭 No active sessions")
                else:
                    msg = "📊 Active Sessions:\n\n"
                    for s, d in list(sessions.items())[:10]:
                        msg += f"🔹 {s}\n   {d['name']}\n\n"
                    send_message(ADMIN_ID, msg)
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
                    send_message(ADMIN_ID, f"✅ Sent to {sid}")
                else:
                    send_message(ADMIN_ID, f"❌ {sid} not found")
        
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({'ok': True})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'sessions': len(sessions),
        'messages': sum(len(m) for m in messages.values())
    })

@app.route('/test-bot', methods=['GET'])
def test_bot():
    """Test if bot token is working"""
    try:
        url = f'{TELEGRAM_API}/getMe'
        with urlopen(url, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            return jsonify({
                'success': result.get('ok', False),
                'bot_info': result.get('result', {}),
                'message': 'Bot is working!' if result.get('ok') else 'Bot token invalid'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/setup-webhook', methods=['GET'])
def setup_webhook():
    """Setup Telegram webhook"""
    try:
        # Force HTTPS for webhook URL (Render always uses HTTPS)
        host = request.host
        webhook_url = f'https://{host}/api/chat/webhook'
        
        logger.info(f"Setting webhook to: {webhook_url}")
        
        # Delete existing webhook first
        delete_url = f'{TELEGRAM_API}/deleteWebhook'
        try:
            with urlopen(delete_url, timeout=10) as response:
                delete_result = json.loads(response.read().decode('utf-8'))
                logger.info(f"Delete webhook: {delete_result}")
        except Exception as e:
            logger.warning(f"Delete webhook failed: {e}")
        
        # Set new webhook
        from urllib.parse import urlencode
        params = urlencode({'url': webhook_url})
        set_url = f'{TELEGRAM_API}/setWebhook?{params}'
        
        logger.info(f"Making request to: {set_url}")
        
        with urlopen(set_url, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            logger.info(f"Set webhook result: {result}")
            
            return jsonify({
                'success': result.get('ok', False),
                'webhook_url': webhook_url,
                'description': result.get('description', ''),
                'error': result.get('description') if not result.get('ok') else None,
                'result': result
            })
    except Exception as e:
        logger.error(f"Webhook setup error: {e}", exc_info=True)
        host = request.host
        return jsonify({
            'success': False,
            'error': str(e),
            'webhook_url': f'https://{host}/api/chat/webhook'
        }), 500

@app.route('/webhook-info', methods=['GET'])
def webhook_info():
    """Get current webhook info"""
    try:
        url = f'{TELEGRAM_API}/getWebhookInfo'
        with urlopen(url, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return jsonify({
        'service': 'Live Chat API',
        'status': 'running',
        'endpoints': {
            'health': '/health',
            'test_bot': '/test-bot - Test if bot token works',
            'webhook_info': '/webhook-info - Check current webhook',
            'setup_webhook': '/setup-webhook - Setup webhook for replies',
            'init_chat': 'POST /api/chat/init',
            'send_message': 'POST /api/chat/send',
            'poll_messages': 'GET /api/chat/poll/<session_id>'
        },
        'setup_steps': [
            '1. Visit /test-bot to verify bot token',
            '2. Visit /setup-webhook to enable replies',
            '3. Check /webhook-info to verify setup',
            '4. Send /start to bot in Telegram'
        ]
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting on port {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
