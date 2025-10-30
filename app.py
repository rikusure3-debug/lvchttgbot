import os
import re
import logging
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS  # flask-cors ইম্পোর্ট করা হয়েছে
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
import httpx  # httpx ইম্পোর্ট করা হয়েছে
import time
import secrets # সিক্রেট কী তৈরির জন্য

# --- কনফিগারেশন ---
TELEGRAM_BOT_TOKEN = "8295821417:AAEZytkScbqqajoK4kw2UyFHt96bKXYOa-A"  # আপনার বট টোকেন
OWNER_CHAT_ID = "2098068100"  # আপনার টেলিগ্রাম চ্যাট আইডি
INTERNAL_API_KEY = "yunus01" # আপনার দেওয়া API কী

# লগিং সেটআপ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("app")

# ইন-মেমোরি স্টোরেজ মেসেজ রাখার জন্য
# { 'session_id_1': [{'from': 'owner', 'message': 'hello'}, {'from': 'visitor', 'message': 'hi'}], ... }
message_store = {}

# সেশন আইডি দিয়ে টেলিগ্রাম চ্যাট আইডি ম্যাপ করার জন্য
session_to_telegram_map = {}

# Flask অ্যাপ ইনিশিয়ালাইজেশন
app = Flask(__name__)
# CORS (Cross-Origin Resource Sharing) সেটআপ করা
CORS(app, resources={
    "/get_player_personal_message": {"origins": ["https://autouidtopup.com", "http://autouidtopup.com", "https://www.autouidtopup.com", "http://www.autouidtopup.com"]},
    "/send_visitor_message": {"origins": ["https://autouidtopup.com", "http://autouidtopup.com", "https://www.autouidtopup.com", "http://www.autouidtopup.com"]}
})

# --- টেলিগ্রাম বট ফাংশন ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start কমান্ড হ্যান্ডলার"""
    if str(update.effective_chat.id) == OWNER_CHAT_ID:
        await update.message.reply_text('API-ভিত্তিক চ্যাট বট চালু হয়েছে। ওয়েবসাইটের ভিজিটরদের মেসেজের জন্য অপেক্ষা করুন।')
    else:
        await update.message.reply_text('আপনি এই বটের অ্যাডমিন নন।')

async def handle_owner_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """মালিকের রিপ্লাই হ্যান্ডল করে"""
    
    if str(update.effective_chat.id) != OWNER_CHAT_ID:
        return

    if update.message.reply_to_message and update.message.reply_to_message.text:
        original_message = update.message.reply_to_message.text
        
        # সেশন আইডি খুঁজে বের করা
        match = re.search(r"\[Visitor: (.*?)\]", original_message)
        
        if match:
            session_id = match.group(1)
            reply_text = update.message.text
            
            # মেসেজটি স্টোরে জমা রাখা
            if session_id not in message_store:
                message_store[session_id] = []
                
            message_store[session_id].append({
                'from': 'owner',
                'message': reply_text,
                'timestamp': time.time()
            })
            
            logger.info(f"মালিকের রিপ্লাই {session_id}-এর জন্য স্টোর করা হয়েছে।")
            await update.message.reply_text("✅ মেসেজটি ভিজিটরের কাছে পাঠানো হয়েছে।")
            
        else:
            await update.message.reply_text("এটি একটি ভিজিটর মেসেজের রিপ্লাই নয়। রিপ্লাই করতে, অনুগ্রহ করে ভিজিটরের মেসেজটি সিলেক্ট করে 'Reply' দিন।")
    else:
        # এটি সাধারণ মেসেজ, কোনো রিপ্লাই নয়
        await update.message.reply_text("ভিজিটরকে উত্তর দিতে, অনুগ্রহ করে তাদের পাঠানো মেসেজটির উপর 'Reply' করুন।")

def run_telegram_bot():
    """টেলিগ্রাম বটটি একটি আলাদা থ্রেডে চালায়"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.REPLY & filters.Chat(chat_id=int(OWNER_CHAT_ID)), 
        handle_owner_reply
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.REPLY & filters.Chat(chat_id=int(OWNER_CHAT_ID)),
        handle_owner_reply 
    ))
    logger.info("টেলিগ্রাম বট পোলিং শুরু করছে...")
    application.run_polling(stop_signals=None)

# --- Flask API এন্ডপয়েন্ট ---

# আপনার দেওয়া URL ফরম্যাটটি একটি GET রিকোয়েস্ট।
# এটি মেসেজ পাওয়ার জন্য ভালো, কিন্তু মেসেজ পাঠানোর জন্য POST ভালো।
# আমি দুটিই তৈরি করে দিচ্ছি।

@app.route('/send_visitor_message', methods=['POST'])
def send_visitor_message():
    """ভিজিটর যখন ওয়েবসাইট থেকে মেসেজ পাঠায়"""
    data = request.json
    
    # API কী ভেরিফিকেশন
    if data.get('key') != INTERNAL_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401
        
    session_id = data.get('session_id')
    message = data.get('message')
    
    if not session_id or not message:
        return jsonify({"error": "session_id and message are required"}), 400

    # মেসেজ স্টোরে জমা রাখা
    if session_id not in message_store:
        message_store[session_id] = []
        # নতুন ভিজিটর এলে টেলিগ্রামে জানানো
        try:
            message_text = f"✅ নতুন ভিজিটর অনলাইন।\n[Visitor: {session_id}]"
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": OWNER_CHAT_ID, "text": message_text}
            # এখানে requests.post ব্যবহার করা নিরাপদ কারণ এটি Flask (gunicorn) থ্রেডে চলছে
            requests.post(url, data=payload)
        except Exception as e:
            logger.error(f"টেলিগ্রামে 'নতুন ভিজিটর' মেসেজ পাঠাতে ব্যর্থ: {e}")
            
    message_store[session_id].append({
        'from': 'visitor',
        'message': message,
        'timestamp': time.time()
    })

    # টেলিগ্রাম মালিককে মেসেজ পাঠানো
    try:
        message_text = f"📩 [Visitor: {session_id}]\n\n{message}"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": OWNER_CHAT_ID, "text": message_text}
        requests.post(url, data=payload)
    except Exception as e:
        logger.error(f"টেলিগ্রামে ভিজিটর মেসেজ পাঠাতে ব্যর্থ: {e}")
        
    logger.info(f"ভিজিটর {session_id} মেসেজ পাঠিয়েছেন: {message}")
    return jsonify({"status": "message_sent"}), 200


@app.route('/get_player_personal_message', methods=['GET'])
def get_player_personal_message():
    """ভিজিটর যখন নতুন মেসেজের জন্য সার্ভারকে চেক করে (Polling)"""
    session_id = request.args.get('session_id')
    api_key = request.args.get('key')
    
    # API কী ভেরিফিকেশন
    if api_key != INTERNAL_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400

    # এই সেশনের জন্য কোনো মেসেজ আছে কিনা চেক করা
    if session_id in message_store:
        # শুধুমাত্র মালিকের (owner) পাঠানো মেসেজগুলো ফিল্টার করা
        owner_messages = [
            msg['message'] for msg in message_store[session_id] if msg['from'] == 'owner'
        ]
        
        if owner_messages:
            # মেসেজগুলো পাওয়ার পর স্টোর থেকে মুছে ফেলা, যাতে আবার না আসে
            message_store[session_id] = [
                msg for msg in message_store[session_id] if msg['from'] != 'owner'
            ]
            
            # সব মেসেজ একটি স্ট্রিং-এ পাঠানো
            full_message = "\n".join(owner_messages)
            logger.info(f"{session_id}-কে {len(owner_messages)} টি নতুন মেসেজ পাঠানো হয়েছে।")
            return jsonify({"status": "new_messages", "message": full_message}), 200

    # কোনো নতুন মেসেজ নেই
    return jsonify({"status": "no_new_messages"}), 200

# --- Flask রুট (সার্ভার চেক করার জন্য) ---
@app.route('/')
def index():
    return "API-ভিত্তিক লাইভ চ্যাট সার্ভার চালু আছে।"

# --- অ্যাপ চালু করা ---
logger.info("টেলিগ্রাম বট থ্রেড চালু করা হচ্ছে...")
bot_thread = Thread(target=run_telegram_bot)
bot_thread.daemon = True
bot_thread.start()
logger.info("টেলিগ্রাম বট থ্রেড সফলভাবে চালু হয়েছে।")

if __name__ == '__main__':
    # এই অংশটি লোকাল টেস্টিং-এর জন্য, Render এটি ব্যবহার করবে না
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Flask সার্ভার {port} পোর্টে চালু হচ্ছে (লোকাল টেস্ট)...")
    app.run(host='0.0.0.0', port=port)

