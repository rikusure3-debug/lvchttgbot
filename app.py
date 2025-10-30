# --- eventlet monkey patch ---
# এটি অবশ্যই ফাইলের একদম শুরুতে থাকতে হবে
# অন্য কোনো import (যেমন flask বা requests) এর আগে
import eventlet
eventlet.monkey_patch()

# --- এখন অন্যান্য মডিউল ইম্পোর্ট করা যাবে ---
import os
import re
import logging
import asyncio
from flask import Flask, send_from_directory, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests

# --- কনফিগারেশন ---
# অনুগ্রহ করে আপনার নতুন টোকেন এখানে ব্যবহার করুন
TELEGRAM_BOT_TOKEN = "8295821417:AAEZytkScbqqajoK4kw2UyFHt96bKXYOa-A"  # আপনার বট টোকেন
OWNER_CHAT_ID = "2098068100"  # আপনার টেলিগ্রাম চ্যাট আইডি

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("app") # Gunicorn এর সাথে ভালো কাজ করার জন্য নাম "app" দিলাম

# Flask এবং SocketIO অ্যাপ ইনিশিয়ালাইজেশন
app = Flask(__name__)
app.config['SECRET_KEY'] = 'render-app-secret-key-123!'

# --- CORS আপডেট ---
# আমরা "*" এর বদলে শুধু আপনার ডোমেইনকে অনুমতি দিচ্ছি
allowed_origins = [
    "https://autouidtopup.com",
    "http://autouidtopup.com",
    "https://www.autouidtopup.com",
    "http://www.autouidtopup.com"
]
socketio = SocketIO(app, cors_allowed_origins=allowed_origins)
# --- /CORS আপডেট ---

# ভিজিটরদের ট্র্যাক করার জন্য
visitor_connections = {}

# --- টেলিগ্রাম বট ফাংশন ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start কমান্ড হ্যান্ডলার"""
    if str(update.effective_chat.id) == OWNER_CHAT_ID:
        await update.message.reply_text('লাইভ চ্যাট বট চালু হয়েছে। ওয়েবসাইটের ভিজিটরদের মেসেজের জন্য অপেক্ষা করুন।')
    else:
        await update.message.reply_text('আপনি এই বটের অ্যাডমিন নন।')

async def handle_owner_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """মালিকের রিপ্লাই হ্যান্ডল করে"""
    
    if str(update.effective_chat.id) != OWNER_CHAT_ID:
        return

    if update.message.reply_to_message and update.message.reply_to_message.text:
        original_message = update.message.reply_to_message.text
        
        match = re.search(r"\[Visitor: (.*?)\]", original_message)
        
        if match:
            session_id = match.group(1)
            reply_text = update.message.text
            
            if session_id in visitor_connections:
                try:
                    # --- সমাধান: asyncio কনফ্লিক্ট এড়ানোর জন্য ব্যাকগ্রাউন্ড টাস্ক ব্যবহার ---
                    def send_reply(sid, text):
                        # আমরা এই টাস্কের মধ্যে emit করছি
                        socketio.emit('server_message', 
                                      {'message': text}, 
                                      room=sid)
                    
                    # SocketIO-কে বলছি এই টাস্কটি তার নিজের মতো করে চালাতে
                    socketio.start_background_task(target=send_reply, sid=session_id, text=reply_text)
                    # --- /সমাধান ---
                    
                    logger.info(f"মালিকের রিপ্লাই {session_id}-কে পাঠানোর জন্য টাস্ক চালু করা হয়েছে।")
                except Exception as e:
                    logger.error(f"SocketIO background task শুরু করতে ব্যর্থ: {e}")
                    await update.message.reply_text(f"ত্রুটি: ভিজিটর {session_id} কে মেসেজ পাঠানো যায়নি (Task Error)।")
            else:
                await update.message.reply_text(f"ভিজিটর {session_id} অফলাইন হয়ে গেছেন। মেসেজ পাঠানো যায়নি।")
        else:
            await update.message.reply_text("এটি একটি ভিজিটর মেসেজের রিপ্লাই নয়। রিপ্লাই করতে, অনুগ্রহ করে ভিজিটরের মেসেজটি সিলেক্ট করে 'Reply' দিন।")
    else:
        await update.message.reply_text("ভিজিটরকে উত্তর দিতে, অনুগ্রহ করে তাদের পাঠানো মেসেজটির উপর 'Reply' করুন।")

def run_telegram_bot():
    """টেলিগ্রাম বটটি চালায়"""

    # এই থ্রেডের জন্য একটি নতুন asyncio ইভেন্ট লুপ তৈরি করুন
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    
    # অ্যাডমিনের রিপ্লাই হ্যান্ডল করার জন্য (সঠিক ফিল্টার সহ)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.REPLY & filters.Chat(chat_id=int(OWNER_CHAT_ID)), 
        handle_owner_reply
    ))
    
    # সাধারণ মেসেজ (যা রিপ্লাই নয়) হ্যান্ডল করার জন্য (সঠিক ফিল্টার সহ)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.REPLY & filters.Chat(chat_id=int(OWNER_CHAT_ID)),
        handle_owner_reply 
    ))

    logger.info("টেলিগ্রাম বট পোলিং শুরু করছে...")
    
    # সিগন্যাল হ্যান্ডলিং বন্ধ করা হয়েছে (থ্রেডে চালানোর জন্য)
    application.run_polling(stop_signals=None)


# --- Flask-SocketIO ইভেন্ট হ্যান্ডলার ---

@socketio.on('connect')
def handle_connect():
    """যখন নতুন কোনো ভিজিটর ওয়েবসাইটে কানেক্ট হয়"""
    session_id = request.sid
    visitor_connections[session_id] = session_id
    join_room(session_id)
    
    logger.info(f"নতুন ভিজিটর কানেক্ট হয়েছেন। সেশন আইডি: {session_id}")
    
    try:
        message_text = f"✅ নতুন ভিজিটর অনলাইন।\n[Visitor: {session_id}]"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": OWNER_CHAT_ID, "text": message_text}
        requests.post(url, data=payload)
    except Exception as e:
        logger.error(f"টেলিগ্রামে কানেকশন মেসেজ পাঠাতে ব্যর্থ: {e}")


@socketio.on('visitor_message')
def handle_visitor_message(data):
    """যখন ভিজিটর ওয়েবসাইট থেকে মেসেজ পাঠায়"""
    session_id = request.sid
    message = data.get('message', '')
    
    if not message:
        return
        
    logger.info(f"ভিজিটর {session_id} মেসেজ পাঠিয়েছেন: {message}")
    
    try:
        message_text = f"📩 [Visitor: {session_id}]\n\n{message}"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": OWNER_CHAT_ID, "text": message_text}
        requests.post(url, data=payload)
    except Exception as e:
        logger.error(f"টেলিগ্রামে ভিজিটর মেসেজ পাঠাতে ব্যর্থ: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    """যখন ভিজিটর ওয়েবসাইট ডিসকানেক্ট করে"""
    session_id = request.sid
    if session_id in visitor_connections:
        leave_room(session_id)
        del visitor_connections[session_id]
        
    logger.info(f"ভিজিটর ডিসকানেক্ট হয়েছেন। সেশন আইডি: {session_id}")
    
    try:
        message_text = f"❌ ভিজিটর অফলাইন।\n[Visitor: {session_id}]"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": OWNER_CHAT_ID, "text": message_text}
        requests.post(url, data=payload)
    except Exception as e:
        logger.error(f"টেলিগ্রামে ডিসকানেকশন মেসেজ পাঠাতে ব্যর্থ: {e}")


# --- Flask রুট (সার্ভার চেক করার জন্য) ---
@app.route('/')
def index():
    return "লাইভ চ্যাট সার্ভার সফলভাবে চালু আছে এবং Render (gunicorn) দিয়ে চলছে।"

# --- অ্যাপ চালু করা ---

# টেলিগ্রাম বটকে একটি আলাদা থ্রেডে (Thread) চালানো
# Gunicorn দিয়ে চালানোর জন্য আমরা এটিকে if-block-এর বাইরে নিয়ে এসেছি
logger.info("টেলিগ্রাম বট থ্রেড চালু করা হচ্ছে...")
bot_thread = Thread(target=run_telegram_bot)
bot_thread.daemon = True
bot_thread.start()
logger.info("টেলিগ্রাম বট থ্রেড সফলভাবে চালু হয়েছে।")

# এই অংশটি শুধু লোকালভাবে 'python app.py' চালিয়ে টেস্ট করার জন্য
# Render বা Gunicorn এই অংশটি ব্যবহার করে না
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"SocketIO সার্ভার {port} পোর্টে চালু হচ্ছে (লোকাল টেস্ট)...")
    socketio.run(app, host='0.0.0.0', port=port)

