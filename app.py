import os
import time
import threading
import json
import re
import requests
from flask import Flask, request
import telebot
from telebot import types
from github import Github, BadCredentialsException
from concurrent.futures import ThreadPoolExecutor, as_completed
import atexit

# ======================
# CONFIG
# ======================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL") 
SESSION_FILE = "bot_sessions.json"
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # Admin's Telegram Chat ID

if not BOT_TOKEN:
    raise SystemExit("❗ BOT_TOKEN environment variable not found!")

# Convert ADMIN_CHAT_ID to integer if provided
if ADMIN_CHAT_ID:
    try:
        ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)
        print(f"✅ Admin Chat ID set: {ADMIN_CHAT_ID}")
    except ValueError:
        print("⚠️ Invalid ADMIN_CHAT_ID format. Admin check disabled.")
        ADMIN_CHAT_ID = None
else:
    print("⚠️ No ADMIN_CHAT_ID set. Bot will work for everyone.")

# ======================
# Setup bot
# ======================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='Markdown')
sessions = {}

# =================================================
# SESSION PERSISTENCE FUNCTIONS
# =================================================
def load_sessions():
    """Load sessions from file on startup"""
    global sessions
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
                # Convert string keys back to integers
                sessions = {int(k): v for k, v in data.items()}
            print(f"✅ Loaded {len(sessions)} sessions from file")
    except Exception as e:
        print(f"⚠️ Could not load sessions: {e}")
        sessions = {}

def save_sessions():
    """Save sessions to file"""
    try:
        # Remove github_client objects as they can't be serialized
        saveable_sessions = {}
        for chat_id, sess in sessions.items():
            clean_sess = {k: v for k, v in sess.items() 
                         if k not in ['github_client', 'repo', 'repos']}
            saveable_sessions[str(chat_id)] = clean_sess
        
        with open(SESSION_FILE, 'w') as f:
            json.dump(saveable_sessions, f, indent=2)
        print(f"💾 Saved {len(saveable_sessions)} sessions")
    except Exception as e:
        print(f"⚠️ Could not save sessions: {e}")

def auto_save_sessions():
    """Periodically save sessions every 5 minutes"""
    while True:
        time.sleep(300)  # 5 minutes
        save_sessions()

# Load sessions on startup
load_sessions()

# Start auto-save thread
save_thread = threading.Thread(target=auto_save_sessions, daemon=True)
save_thread.start()

# Save sessions on exit
atexit.register(save_sessions)

# =================================================
# ADMIN CHECK FUNCTION
# =================================================
def is_admin(chat_id):
    """Check if user is admin. If no ADMIN_CHAT_ID set, allow everyone."""
    if ADMIN_CHAT_ID is None:
        return True  # No admin restriction
    return chat_id == ADMIN_CHAT_ID

def admin_only(func):
    """Decorator to restrict commands to admin only"""
    def wrapper(message):
        if not is_admin(message.chat.id):
            bot.send_message(
                message.chat.id,
                "🚫 *Access Denied!*\n\n"
                "This bot is restricted to authorized users only.\n"
                "Please contact the bot administrator for access."
            )
            return
        return func(message)
    return wrapper

# =================================================
# UTILITY FUNCTIONS (All 3 bots combined)
# =================================================
def get_session(chat_id):
    """Return or create a user session."""
    if chat_id not in sessions:
        sessions[chat_id] = {"step": None}
    
    # Restore GitHub client if token exists but client doesn't
    sess = sessions[chat_id]
    if sess.get("github_token") and not sess.get("github_client"):
        try:
            sess["github_client"] = Github(sess["github_token"])
            print(f"♻️ Restored GitHub client for user {chat_id}")
        except Exception as e:
            print(f"⚠️ Could not restore GitHub client: {e}")
    
    return sessions[chat_id]

# --- GitHub Editor Utilities ---
def list_repo_files(repo, path=""):
    result = []
    try:
        contents = repo.get_contents(path)
        for item in contents:
            if item.type == "dir":
                result.extend(list_repo_files(repo, item.path))
            else:
                result.append(item.path)
    except Exception: pass
    return result

def send_numbered_list(chat_id, items, title="Items", per_page=50):
    if not items:
        bot.send_message(chat_id, f"⚠️ No {title.lower()} found."); return
    text = f"*{title}* — total: {len(items)}\n\n"
    for i, item in enumerate(items[:per_page], 1):
        text += f"{i}. `{item}`\n"
    if len(items) > per_page:
        text += f"\n_Showing first {per_page}._"
    bot.send_message(chat_id, text)

# --- JWT Token Generator Utilities ---
def fetch_jwt_token(account):
    uid, password = account.get("uid"), account.get("password")
    if not uid or not password: return None
    url = f"https://jwt-yunus-new.vercel.app/token?uid={uid}&password={password}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and (token := response.json().get("token")):
            return {"token": token}
    except Exception as e:
        print(f"Request failed for UID {uid}: {e}")
    return None

# --- JSON Converter Utilities (NEW!) ---
_uid_re = re.compile(r'"?\buid\b"?\s*:\s*(?P<val>"[^"]*"|[0-9]+)', re.I)
_password_re = re.compile(r'"?\bpass(?:word)?\b"?\s*:\s*(?P<val>"[^"]*"|[^,\}\n]+)', re.I)

def try_parse_json(text: str):
    text = re.sub(r',\s*(?=[}\]])', '', text.strip())
    wrapped = f'[{text}]' if text.startswith('{') and not text.startswith('[') else text
    parsed = json.loads(wrapped)
    if isinstance(parsed, dict): return [parsed]
    if isinstance(parsed, list): return [item for item in parsed if isinstance(item, dict)]
    raise ValueError("Parsed data is not a list or dict")

def parse_by_blocks(text: str):
    s = re.sub(r',\s*(?=})', '', text.replace('\r\n', '\n').strip())
    parts = re.split(r'\}\s*,\s*\{', s)
    results, seen = [], set()
    for p in parts:
        block = '{' + p.strip() if not p.strip().startswith('{') else p.strip()
        block = block + '}' if not block.endswith('}') else block
        uid_m = _uid_re.search(block)
        pass_m = _password_re.search(block)
        if uid_m and pass_m:
            uid = uid_m.group('val').strip().strip('"')
            pwd = pass_m.group('val').strip().strip('"')
            if (uid, pwd) not in seen:
                results.append({"uid": uid, "password": pwd})
                seen.add((uid, pwd))
    return results

def extract_uid_password_pairs(text: str):
    try:
        objs = try_parse_json(text)
        res, seen = [], set()
        for o in objs:
            uid_val, pass_val = None, None
            for k, v in o.items():
                kl = k.lower()
                if kl in ("uid", "user", "user_id", "id"): uid_val = str(v)
                if kl in ("password", "pass", "pwd"): pass_val = str(v)
            if uid_val and pass_val and (uid_val, pass_val) not in seen:
                res.append({"uid": uid_val, "password": pass_val})
                seen.add((uid_val, pass_val))
        if res: return res
    except Exception: pass
    
    res = parse_by_blocks(text)
    if res: return res
    
    return []

# =================================================
# KEYBOARD & COMMANDS
# =================================================
@bot.message_handler(commands=['start'])
@admin_only
def cmd_start(message):
    chat_id = message.chat.id
    sess = get_session(chat_id)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_github = types.InlineKeyboardButton("🐙 GitHub Editor", callback_data="github_start")
    btn_jwt = types.InlineKeyboardButton("🔑 JWT Generator", callback_data="jwt_generator_start")
    btn_json = types.InlineKeyboardButton("⚙️ JSON Converter", callback_data="json_converter_start")
    markup.add(btn_github, btn_jwt, btn_json)
    
    welcome_text = "👋 *Welcome to your 3-in-1 Super-Bot!*\n\n"
    
    # Show if session was restored
    if sess.get("github_token"):
        welcome_text += "♻️ _Your GitHub session has been restored!_\n\n"
    
    welcome_text += "Please choose a task from the menu:"
    
    bot.send_message(chat_id, welcome_text, reply_markup=markup)

@bot.message_handler(commands=['cancel'])
@admin_only
def cmd_cancel(message):
    sessions.pop(message.chat.id, None)
    save_sessions()  # Save after clearing session
    bot.send_message(message.chat.id, "✅ Operation cancelled. Press /start to see the menu.")

@bot.message_handler(commands=['myid'])
def cmd_myid(message):
    """Show user's chat ID - works for everyone"""
    chat_id = message.chat.id
    user_info = message.from_user
    
    info_text = (
        f"👤 *Your Information:*\n\n"
        f"🆔 Chat ID: `{chat_id}`\n"
        f"👤 Username: @{user_info.username or 'Not set'}\n"
        f"📛 Name: {user_info.first_name or ''} {user_info.last_name or ''}\n\n"
    )
    
    if is_admin(chat_id):
        info_text += "✅ *You are an admin!*"
    else:
        info_text += "❌ *You are not an admin.*\n\n_To set up admin access, add your Chat ID to the `ADMIN_CHAT_ID` environment variable._"
    
    bot.send_message(chat_id, info_text)

@bot.message_handler(commands=['status'])
@admin_only
def cmd_status(message):
    """Show current session status"""
    chat_id = message.chat.id
    sess = get_session(chat_id)
    
    status_text = "📊 *Your Session Status:*\n\n"
    
    if sess.get("github_token"):
        status_text += "🐙 *GitHub:* Connected ✅\n"
    else:
        status_text += "🐙 *GitHub:* Not connected ❌\n"
    
    if sess.get("step"):
        status_text += f"📍 *Current Step:* `{sess['step']}`\n"
    else:
        status_text += "📍 *Current Step:* Idle\n"
    
    status_text += f"\n💾 Sessions will persist across restarts!"
    
    bot.send_message(chat_id, status_text)

# =================================================
# CALLBACK HANDLER (Handles button clicks)
# =================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    chat_id = call.message.chat.id
    
    # Admin check
    if not is_admin(chat_id):
        bot.answer_callback_query(call.id, "🚫 Access Denied!", show_alert=True)
        return
    
    sess = get_session(chat_id)
    bot.answer_callback_query(call.id)

    if call.data == "github_start":
        bot.edit_message_text("Selected: *🐙 GitHub Editor*", chat_id, call.message.message_id)
        if not sess.get("github_client"):
            sess["step"] = "ask_github_token"
            bot.send_message(chat_id, "Please send your *GitHub Personal Access Token* to continue.")
        else:
            list_github_repos(call.message)

    elif call.data == "jwt_generator_start":
        bot.edit_message_text("Selected: *🔑 JWT Generator*", chat_id, call.message.message_id)
        sess['step'] = 'awaiting_jwt_json'
        bot.send_message(chat_id, "Please upload the JSON file with accounts (`uid` and `password`).")

    elif call.data == "json_converter_start":
        bot.edit_message_text("Selected: *⚙️ JSON Converter*", chat_id, call.message.message_id)
        sess['step'] = 'awaiting_json_text_or_file'
        bot.send_message(
            chat_id, 
            "📋 *JSON Converter*\n\n"
            "Send me account details in any of these formats:\n"
            "• 📝 Text message (copy-paste accounts)\n"
            "• 📄 Text/JSON file\n\n"
            "❌ *Not supported:* Voice messages, Images\n\n"
            "I will extract `uid` and `password` pairs into a clean JSON file."
        )

# =================================================
# GITHUB WORKFLOW LOGIC
# =================================================
def list_github_repos(message):
    # This function remains unchanged
    chat_id = message.chat.id
    sess = get_session(chat_id)
    bot.send_message(chat_id, "⏳ Fetching your GitHub repositories...")
    try:
        repos = list(sess["github_client"].get_user().get_repos())
        if not repos: bot.send_message(chat_id, "⚠️ No repositories found."); return
        sess.update({'repos': [(r.full_name, r) for r in repos], 'step': 'select_repo'})
        send_numbered_list(chat_id, [r.full_name for r in repos], title="Your Repositories")
        bot.send_message(chat_id, "➡️ Send the *number* or *full name* of the repo to open.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error fetching repos:\n`{e}`")

# =================================================
# MESSAGE HANDLERS
# =================================================
@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    
    # Admin check
    if not is_admin(chat_id):
        bot.send_message(
            chat_id,
            "🚫 *Access Denied!*\n\n"
            "This bot is restricted to authorized users only."
        )
        return
    
    text = message.text.strip()
    sess = get_session(chat_id)

    # --- GitHub Editor Workflow ---
    if sess.get("step") == "ask_github_token":
        try:
            github_client = Github(text)
            github_client.get_user().login
            sess.update({"github_token": text, "github_client": github_client, "step": None})
            save_sessions()  # Save after token is stored
            bot.send_message(chat_id, "✅ GitHub token saved! Now listing repositories...")
            list_github_repos(message)
        except Exception as e:
            bot.send_message(chat_id, f"❌ Invalid GitHub token or error: `{e}`.")
        return

    if sess.get('step') == 'select_repo':
        repo = next((r for name, r in sess['repos'] if name.lower() == text.lower()), None)
        if not repo:
            try: repo = sess['repos'][int(text) - 1][1]
            except (ValueError, IndexError): bot.send_message(chat_id, "⚠️ Invalid repo."); return
        sess.update({'repo': repo, 'step': 'select_file'})
        bot.send_message(chat_id, f"✅ Selected: *{repo.full_name}*\n⏳ Listing files...")
        files = list_repo_files(repo)
        sess['files'] = files
        if not files: bot.send_message(chat_id, "⚠️ No files found."); sess['step'] = None; return
        send_numbered_list(chat_id, files, title="Files in Repo")
        bot.send_message(chat_id, "➡️ Send *file number* or *path* to edit.")
        return

    if sess.get('step') == 'select_file':
        file_path = text
        if text.isdigit() and 1 <= int(text) <= len(sess['files']):
            file_path = sess['files'][int(text) - 1]
        try:
            file_data = sess['repo'].get_contents(file_path)
            sess.update({'file_path': file_path, 'file_sha': file_data.sha, 'step': 'edit_file'})
            content = file_data.decoded_content.decode('utf-8', 'ignore')
            bot.send_message(chat_id, f"*Current content of `{file_path}`:*\n\n```\n{content[:3500]}\n```")
            bot.send_message(chat_id, "✏️ Send new text or upload a file to replace.")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error reading file `{file_path}`:\n`{e}`")
        return

    if sess.get('step') == 'edit_file':
        try:
            sess['repo'].update_file(sess['file_path'], f"Updated via Telegram", text, sess['file_sha'])
            bot.send_message(chat_id, f"✅ File `{sess['file_path']}` updated!")
            sess['step'] = None
        except Exception as e:
            bot.send_message(chat_id, f"❌ Failed to update file:\n`{e}`")
        return

    # --- JSON Converter Workflow (NEW!) ---
    if sess.get('step') == 'awaiting_json_text_or_file':
        accounts = extract_uid_password_pairs(text)
        if not accounts:
            bot.send_message(chat_id, "⚠️ Could not find any `uid`/`password` pairs in the text.")
            return
        filename = f"converted_{chat_id}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=4)
        with open(filename, "rb") as f:
            bot.send_document(message.chat.id, f, caption=f"✅ Extracted {len(accounts)} accounts.")
        os.remove(filename)
        sess['step'] = None
        return

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    
    # Admin check
    if not is_admin(chat_id):
        bot.send_message(
            chat_id,
            "🚫 *Access Denied!*\n\n"
            "This bot is restricted to authorized users only."
        )
        return
    
    sess = get_session(chat_id)
    doc = message.document
    file_info = bot.get_file(doc.file_id)
    data = bot.download_file(file_info.file_path)

    # --- GitHub Editor Workflow ---
    if sess.get('step') == 'edit_file':
        try:
            text = data.decode('utf-8')
            sess['repo'].update_file(sess['file_path'], f"Updated via upload", text, sess['file_sha'])
            bot.send_message(chat_id, f"✅ File `{sess['file_path']}` updated via upload.")
            sess['step'] = None
        except Exception as e:
            bot.send_message(chat_id, f"❌ Update failed:\n`{e}`")
        return

    # --- JWT Generator Workflow ---
    if sess.get('step') == 'awaiting_jwt_json' and doc.file_name.lower().endswith('.json'):
        msg = bot.send_message(chat_id, "✅ JSON received! Generating JWTs...")
        try:
            accounts = json.loads(data.decode('utf-8'))
            if not isinstance(accounts, list):
                bot.edit_message_text("❌ Error: JSON must be a list `[...]`.", chat_id, msg.message_id); return
        except Exception as e:
            bot.edit_message_text(f"❌ Failed to parse JSON: `{e}`", chat_id, msg.message_id); return
        
        total = len(accounts)
        tokens_list = []
        success_count = 0
        fail_count = 0
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(fetch_jwt_token, acc) for acc in accounts]
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result:
                    tokens_list.append(result)
                    success_count += 1
                else:
                    fail_count += 1
                
                if i % 5 == 0 or i == total:
                    status_text = (
                        f"⏳ *Processing JWTs...*\n\n"
                        f"📊 Progress: {i}/{total}\n"
                        f"✅ Success: {success_count}\n"
                        f"❌ Failed: {fail_count}\n"
                        f"📈 Success Rate: {(success_count/i*100):.1f}%"
                    )
                    try: bot.edit_message_text(status_text, chat_id, msg.message_id)
                    except telebot.apihelper.ApiTelegramException: pass
        
        output_filename = f"jwts_{chat_id}.json"
        with open(output_filename, "w") as f: json.dump(tokens_list, f, indent=4)
        
        final_text = (
            f"✅ *Generation Complete!*\n\n"
            f"📊 Total Accounts: {total}\n"
            f"✅ Successful: {success_count}\n"
            f"❌ Failed: {fail_count}\n"
            f"📈 Success Rate: {(success_count/total*100):.1f}%"
        )
        bot.edit_message_text(final_text, chat_id, msg.message_id)
        
        with open(output_filename, "rb") as f: 
            bot.send_document(chat_id, f, caption=f"🎉 Here are your {success_count} JWT tokens!")
        os.remove(output_filename)
        sess['step'] = None
        return

    # --- JSON Converter Workflow ---
    if sess.get('step') == 'awaiting_json_text_or_file':
        content = data.decode('utf-8', 'ignore')
        accounts = extract_uid_password_pairs(content)
        if not accounts:
            bot.send_message(chat_id, "⚠️ No `uid`/`password` pairs found in the file.")
            return
        filename = f"converted_{chat_id}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=4)
        with open(filename, "rb") as f:
            bot.send_document(message.chat.id, f, caption=f"✅ Extracted {len(accounts)} accounts from file.")
        os.remove(filename)
        sess['step'] = None
        return

    bot.send_message(chat_id, "⚠️ Not sure what to do. Use /start to select a task first.")

@bot.message_handler(content_types=['voice', 'audio'])
def handle_voice_audio(message):
    """Handle voice messages and audio files - currently not supported"""
    chat_id = message.chat.id
    
    # Admin check
    if not is_admin(chat_id):
        bot.send_message(
            chat_id,
            "🚫 *Access Denied!*\n\n"
            "This bot is restricted to authorized users only."
        )
        return
    
    bot.send_message(
        chat_id, 
        "⚠️ *Voice/Audio messages are not supported.*\n\n"
        "Please send:\n"
        "• 📝 Text message with account details\n"
        "• 📄 Text/JSON file\n"
        "• 🖼️ Image (screenshot of accounts)\n\n"
        "Voice messages cannot be processed by this bot."
    )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    """Handle photo/image uploads - extract text using OCR if needed"""
    chat_id = message.chat.id
    
    # Admin check
    if not is_admin(chat_id):
        bot.send_message(
            chat_id,
            "🚫 *Access Denied!*\n\n"
            "This bot is restricted to authorized users only."
        )
        return
    
    sess = get_session(chat_id)
    
    if sess.get('step') == 'awaiting_json_text_or_file':
        bot.send_message(
            chat_id,
            "📸 *Image received!*\n\n"
            "⚠️ To extract account details from images, please:\n"
            "1. Use a text recognition app to convert the image to text\n"
            "2. Send the text directly, or\n"
            "3. Send a text/JSON file instead\n\n"
            "_Image OCR is not currently supported._"
        )
        return
    
    bot.send_message(
        chat_id,
        "🖼️ Image received, but I'm not sure what to do with it.\n"
        "Please use /start to select a task first."
    )

# =================================================
# FLASK SERVER & WEBHOOK (Unchanged)
# =================================================
app = Flask(__name__)
@app.route("/")
def home(): return "✅ Super-Bot is running!"

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def get_message():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    else:
        return "Unsupported Media Type", 415

if __name__ == "__main__":
    print("🤖 Super-Bot is starting with webhooks...")
    bot.remove_webhook()
    time.sleep(0.5)
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    print(f"Webhook set to {WEBHOOK_URL}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
