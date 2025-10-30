# 🚀 Telegram Live Chat System - Complete Setup (File Support Added!)

## ✨ Features
- ✅ Website e live chat widget
- ✅ **File/Image upload support** 
- ✅ Telegram bot diye admin respond kore
- ✅ Session ID automatic routing
- ✅ Real-time messaging
- ✅ No focus/unfocus needed
- ✅ Simple reply system

---

## 📦 Your Configuration (Already Set!)

```
Telegram Bot Token: 8295821417:AAEZytkScbqqajoK4kw2UyFHt96bKXYOa-A
Admin Chat ID: 2098068100
Render URL: https://lvchttgbot.onrender.com
```

---

## 🔧 Render e Deploy Koro

### Step 1: Files Upload Koro
1. GitHub repository banao (or existing one e)
2. 2ta file upload koro:
   - `app.py` (Python code artifact theke)
   - `requirements.txt`

### Step 2: Render Configuration
1. [render.com](https://render.com) e login koro
2. "New" → "Web Service" 
3. GitHub repo connect koro
4. Settings:
   - **Name**: lvchttgbot (or jekono naam)
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`

### Step 3: Environment Variables
Render dashboard e "Environment" section e:

```bash
TELEGRAM_BOT_TOKEN = 8295821417:AAEZytkScbqqajoK4kw2UyFHt96bKXYOa-A
ADMIN_CHAT_ID = 2098068100
PORT = 5000
```

**Deploy** button press koro!

---

## 🌐 Website e Chat Widget Setup

### HTML File e Code Add Koro

Widget HTML file already configure kora ache with:
```javascript
const API_URL = 'https://lvchttgbot.onrender.com/api/chat';
```

Simply copy-paste kore tumhar website e add koro. Widget automatic bottom-right corner e show hobe.

---

## 💬 Kemon Kaaj Kore

### 1. Text Message

**Visitor Side:**
- Chat open kore
- Message likhe: "Product er dam koto?"

**Telegram e tumi pabe:**
```
💬 New Message from Website

🆔 Session: SES_20241031120530
👤 User: Kamal Ahmed
📧 Email: kamal@example.com
💭 Message: Product er dam koto?

📝 Reply: SES_20241031120530: Tumhar reply
```

**Tumi reply koro:**
```
SES_20241031120530: 5000 taka
```

---

### 2. File/Image Upload

**Visitor Side:**
- Attach button click kore
- File/image select kore
- Optional message likhe
- Send kore

**Telegram e tumi pabe:**
```
💬 New Message from Website

🆔 Session: SES_20241031120530
👤 User: Kamal Ahmed
📎 File: product_image.jpg
💭 Message: Eta dekhun

📝 Reply: SES_20241031120530: Tumhar reply
```

**Photo/File er sathe image/document ashbe**

**Tumi reply korte paro:**

#### Text Reply:
```
SES_20241031120530: Hain, eta available ache
```

#### Photo Reply:
1. Photo upload koro Telegram e
2. Caption e likho:
```
SES_20241031120530: Dekhen eta emon
```

#### File Reply:
1. Document send koro Telegram e
2. Caption e likho:
```
SES_20241031120530: Ei brochure dekhen
```

---

## 🎯 Supported File Types

### Visitor Upload Korte Pare:
- ✅ Images: JPG, PNG, GIF, WebP
- ✅ Documents: PDF, DOC, DOCX, TXT
- ✅ Any file type (10MB limit recommended)

### Admin Send Korte Pare:
- ✅ Photos (Telegram er through)
- ✅ Documents (PDF, DOC, etc.)
- ✅ Any file Telegram support kore

---

## 🔍 Telegram Bot Commands

```
/start - Bot activate
/sessions - Active sessions list
```

### Reply Format:

**Text only:**
```
SES_12345: Tumhar message
```

**Photo with message:**
1. Photo upload koro
2. Caption: `SES_12345: Tumhar message`

**File with message:**
1. Document send koro
2. Caption: `SES_12345: Tumhar message`

---

## ⚙️ API Endpoints

```
POST /api/chat/init - Start new session
POST /api/chat/send - Send text message
POST /api/chat/upload - Upload file
GET /api/chat/file/<file_id> - Download file
GET /api/chat/poll/<session_id> - Poll new messages
GET /health - Health check
```

---

## 🛠️ Troubleshooting

### Bot respond korche na?
1. Render logs check koro: Dashboard → Logs
2. Environment variables thik ache ki verify koro
3. Bot token copy-paste correctly done ki check koro

### File upload hocche na?
1. File size 10MB er kom ki na check koro
2. Browser console e error dekho
3. Network tab e upload request inspect koro

### Telegram e notification ashche na?
1. Bot e `/start` command pathao
2. Admin Chat ID thik ache ki verify koro
3. Bot token active ache ki check koro (BotFather e)

### Message reply jachhe na?
1. Session ID exactly match korche ki check koro
2. Colon (`:`) properly use korecho ki
3. Format strictly follow koro: `SES_xxxxx: Message`

---

## 🚀 Production Tips

### 1. Database Setup (Important!)
In-memory storage production er jonno safe na. Use koro:
- **PostgreSQL** on Render (free tier available)
- **MongoDB Atlas** (free tier)
- **Redis** for caching

### 2. File Storage
Large files er jonno:
- **AWS S3** bucket use koro
- **Cloudinary** for images
- **Google Cloud Storage**

### 3. Security
- Rate limiting implement koro
- File size validation add koro
- Malware scanning add koro uploaded files er jonno
- CORS properly configure koro

### 4. Performance
- CDN use koro static files er jonno
- Redis caching implement koro
- Database indexing properly setup koro

### 5. Monitoring
- Render e auto-restart enable koro
- Uptime monitoring tool use koro (UptimeRobot)
- Error logging setup koro (Sentry)

---

## 📊 Testing Checklist

Before going live:

- [ ] Bot `/start` command test kora
- [ ] Text message send/receive test
- [ ] Image upload test (visitor side)
- [ ] File upload test (visitor side)
- [ ] Photo reply test (admin side)
- [ ] File reply test (admin side)
- [ ] Session ID routing test
- [ ] Multiple sessions test
- [ ] Mobile responsive test
- [ ] Error handling test

---

## 🎉 Quick Start Commands

### Test Health:
```bash
curl https://lvchttgbot.onrender.com/health
```

### Initialize Chat (curl):
```bash
curl -X POST https://lvchttgbot.onrender.com/api/chat/init \
  -H "Content-Type: application/json" \
  -d '{"name":"Test User","email":"test@example.com"}'
```

---

## 📝 Example Widget Integration

### WordPress:
```php
<?php
// Add to footer.php or use a custom HTML widget
?>
<!-- Paste complete widget HTML here -->
```

### React:
```jsx
// Create a component
import ChatWidget from './components/ChatWidget';

function App() {
  return (
    <div>
      <ChatWidget />
    </div>
  );
}
```

### Plain HTML:
Simply paste the widget HTML before `</body>` tag.

---

## 🔐 Security Notes

1. **NEVER** commit tokens to GitHub
2. Use environment variables always
3. Add `.env` to `.gitignore`
4. Rotate tokens if exposed
5. Validate all user inputs
6. Sanitize file uploads

---

## 📞 Support

Kono problem hole:
1. Render logs check koro
2. Browser console check koro
3. Telegram bot logs check koro
4. GitHub e issue create koro (if public repo)

---

## ✅ All Set!

Tumhar live chat system file support soho ready! 

Test koro:
1. Website e jao
2. Chat widget open koro
3. Message + file send koro
4. Telegram e notification check koro
5. Reply koro and test!

Happy Chatting! 🎉
