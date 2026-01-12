# 🥋 دليل ربط فيسبوك - أكاديمية أبطال أكتوبر

## 📋 نظرة عامة

هذا الدليل يشرح كيفية ربط التطبيق بصفحة فيسبوك لـ:

- ✅ الرد التلقائي على الرسائل (Messenger)
- ✅ الرد على التعليقات (Comments)
- ✅ نشر المحتوى المُولَّد

---

## 🎯 الخطوة 1: إنشاء Facebook App

### 1.1 إنشاء التطبيق

1. اذهب إلى [Facebook Developers](https://developers.facebook.com/apps/)
2. اضغط **Create App**
3. اختر نوع: **Business**
4. املأ البيانات:
   - **App Name**: Academy Manager Bot
   - **App Contact Email**: بريدك الإلكتروني
5. اضغط **Create App**

### 1.2 إضافة المنتجات

من لوحة التحكم، أضف هذه المنتجات:

#### أ) Messenger

1. اضغط **Set Up** على Messenger
2. في **Access Tokens**:
   - اضغط **Add or Remove Pages**
   - اختر صفحة **october.heroes.academy**
   - اضغط **Generate Token**
   - **احفظ الـ Token** - ستحتاجه لاحقاً

#### ب) Webhooks

1. اضغط **Set Up** على Webhooks
2. سنعود لهذا بعد رفع التطبيق

---

## 🚀 الخطوة 2: رفع التطبيق على Streamlit Cloud

### 2.1 رفع على GitHub

```bash
cd "f:\Raw\New folder"
git init
git add .
git commit -m "Initial commit - Academy Manager"
git branch -M main
git remote add origin https://github.com/m0shaban/academy-manager.git
git push -u origin main
```

### 2.2 النشر على Streamlit

1. اذهب إلى [share.streamlit.io](https://share.streamlit.io)
2. سجل دخول بحساب GitHub
3. اضغط **New app**
4. املأ البيانات:
   - **Repository**: `m0shaban/academy-manager`
   - **Branch**: `main`
   - **Main file path**: `app.py`
5. في **Advanced settings** → **Secrets**، أضف:

```toml
GROQ_API_KEY_4 = "MOVED_TO_SECRETS"
NVIDIA_API_KEY = "MOVED_TO_SECRETS"
IMGBB_API_KEY = "MOVED_TO_SECRETS"
```

1. اضغط **Deploy!**
2. انتظر 2-3 دقائق
3. **احفظ الرابط** (مثال: `https://academy-manager-xyz.streamlit.app`)

---

## 🔗 الخطوة 3: إنشاء Webhook Endpoint

### 3.1 إنشاء ملف webhook منفصل

سنحتاج لعمل **Flask API** منفصل للـ Webhooks لأن Streamlit لا يدعم POST requests مباشرة.

**خياران:**

#### الخيار الأول: استخدام Render (مجاني)

1. أنشئ ملف `webhook.py` في المشروع
2. ارفعه على Render كـ Web Service
3. استخدم الرابط في Facebook

#### الخيار الثاني: استخدام Replit (أسهل)

1. اذهب إلى [replit.com](https://replit.com)
2. أنشئ Python Repl جديد
3. انسخ كود الـ webhook (سأعطيك إياه)
4. شغّل واحصل على الرابط

---

## 📝 الخطوة 4: كود Webhook (Flask)

أنشئ ملف `webhook.py`:

```python
from flask import Flask, request, jsonify
import os
from groq import Groq

app = Flask(__name__)

# API Keys
GROQ_API_KEY = os.environ.get("GROQ_API_KEY_4")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = "academy_webhook_2026"  # اختر كلمة سر

# Initialize Groq
client = Groq(api_key=GROQ_API_KEY)

# Academy Data (نفس البيانات من academy_data.json)
ACADEMY_DATA = {
    "academy_name": "أكاديمية أبطال أكتوبر",
    "manager": "كابتن عز غريب",
    "phone": "01004945997",
    "phone_alt": "01033111786",
    "location": "الحي الثاني، المجاورة السابعة، عمارة 2151، مدينة 6 أكتوبر",
    "schedules": {
        "كاراتيه": ["الأحد والثلاثاء والخميس - 4:30 م"],
        "كونغ فو": ["الاثنين والأربعاء - 6:00 م"],
        "كيك بوكسينج": ["الأحد والثلاثاء والأربعاء - 7:30 م"],
        "جمباز": ["الاثنين والخميس - 3:00 م و 5:30 م"],
    },
    "pricing": {
        "كاراتيه": "500 جنيه/شهر",
        "كونغ فو": "500 جنيه/شهر",
        "كيك بوكسينج": "500 جنيه/شهر",
        "جمباز": "600 جنيه/شهر",
    },
    "offers": [
        "🎉 بمناسبة العام الجديد - بادر بالحجز!",
        "💪 اشتراك شهري 500 جنيه للكاراتيه والكونغ فو!",
    ]
}

SYSTEM_PROMPT = """أنت كابتن عز غريب - مدير أكاديمية أبطال أكتوبر.
رد بالعربية المصرية، كن ودود ومحترف، شجع على التسجيل."""

def generate_response(message):
    """Generate AI response using Groq"""
    context = f"""
معلومات الأكاديمية:
- الاسم: {ACADEMY_DATA['academy_name']}
- المدير: {ACADEMY_DATA['manager']}
- الهاتف: {ACADEMY_DATA['phone']} أو {ACADEMY_DATA['phone_alt']}
- العنوان: {ACADEMY_DATA['location']}

المواعيد: {ACADEMY_DATA['schedules']}
الأسعار: {ACADEMY_DATA['pricing']}
العروض: {ACADEMY_DATA['offers']}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + context},
                {"role": "user", "content": message}
            ],
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content
    except:
        return "عذراً، حدث خطأ. تواصل معنا على 01004945997"

def send_message(recipient_id, message_text):
    """Send message via Facebook Messenger API"""
    import requests

    url = f"https://graph.facebook.com/v18.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }

    requests.post(url, params=params, json=data)

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Webhook verification"""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("✅ Webhook verified!")
        return challenge, 200

    return 'Forbidden', 403

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handle incoming messages"""
    data = request.get_json()

    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            # Handle Messages
            for messaging in entry.get('messaging', []):
                sender_id = messaging['sender']['id']

                if 'message' in messaging:
                    message_text = messaging['message'].get('text', '')

                    # Generate response
                    response = generate_response(message_text)

                    # Send back
                    send_message(sender_id, response)

            # Handle Comments
            for change in entry.get('changes', []):
                if change.get('field') == 'feed':
                    value = change.get('value', {})
                    if value.get('item') == 'comment':
                        comment_id = value.get('comment_id')
                        message = value.get('message', '')

                        # Generate response
                        response = generate_response(message)

                        # Reply to comment
                        reply_to_comment(comment_id, response)

    return 'OK', 200

def reply_to_comment(comment_id, message):
    """Reply to a Facebook comment"""
    import requests

    url = f"https://graph.facebook.com/v18.0/{comment_id}/comments"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"message": message}

    requests.post(url, params=params, json=data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

---

## 🔧 الخطوة 5: رفع Webhook على Render

### 5.1 إنشاء ملفات إضافية

**ملف `requirements-webhook.txt`:**

```
flask
groq
requests
gunicorn
```

**ملف `render.yaml`:**

```yaml
services:
  - type: web
    name: academy-webhook
    env: python
    buildCommand: pip install -r requirements-webhook.txt
    startCommand: gunicorn webhook:app
    envVars:
      - key: GROQ_API_KEY_4
        sync: false
      - key: PAGE_ACCESS_TOKEN
        sync: false
```

### 5.2 الرفع على Render

1. اذهب إلى [render.com](https://render.com)
2. سجل دخول بـ GitHub
3. اضغط **New** → **Web Service**
4. اختر الـ repo: `m0shaban/academy-manager`
5. املأ:
   - **Name**: `academy-webhook`
   - **Build Command**: `pip install -r requirements-webhook.txt`
   - **Start Command**: `gunicorn webhook:app`
6. في **Environment Variables**:
   - `GROQ_API_KEY_4` = مفتاح Groq
   - `PAGE_ACCESS_TOKEN` = Token من Facebook (الخطوة 1.2)
7. اضغط **Create Web Service**
8. **احفظ الرابط** (مثال: `https://academy-webhook.onrender.com`)

---

## 🎯 الخطوة 6: ربط Webhook بـ Facebook

### 6.1 إعداد Webhooks

1. ارجع لـ Facebook App
2. اذهب إلى **Messenger** → **Settings**
3. في **Webhooks**:
   - **Callback URL**: `https://academy-webhook.onrender.com/webhook`
   - **Verify Token**: `academy_webhook_2026`
   - اضغط **Verify and Save**

### 6.2 الاشتراك في الأحداث

1. اضغط **Add Subscriptions**
2. اختر:
   - ✅ `messages`
   - ✅ `messaging_postbacks`
   - ✅ `feed` (للتعليقات)
3. اضغط **Save**

---

## ✅ الخطوة 7: الاختبار

### 7.1 اختبار الرسائل

1. اذهب لصفحة الفيسبوك
2. ابعت رسالة: "كام سعر الكاراتيه؟"
3. البوت المفروض يرد تلقائياً!

### 7.2 اختبار التعليقات

1. انشر أي منشور على الصفحة
2. علق: "في عروض؟"
3. البوت يرد على التعليق!

---

## 🎁 الخطوة 8: نشر المحتوى (اختياري)

لنشر المحتوى المُولَّد من التطبيق على الصفحة مباشرة:

```python
def post_to_facebook(message, image_url=None):
    import requests

    url = f"https://graph.facebook.com/v18.0/{PAGE_ID}/feed"
    params = {"access_token": PAGE_ACCESS_TOKEN}

    data = {"message": message}
    if image_url:
        data["link"] = image_url

    response = requests.post(url, params=params, json=data)
    return response.json()
```

---

## 📊 ملخص الخطوات

| الخطوة | الوصف                     | الحالة |
| ------ | ------------------------- | ------ |
| 1      | إنشاء Facebook App        | ⏳     |
| 2      | رفع على Streamlit Cloud   | ⏳     |
| 3      | رفع Webhook على Render    | ⏳     |
| 4      | ربط Webhook بـ Facebook   | ⏳     |
| 5      | اختبار الرسائل والتعليقات | ⏳     |

---

## 🆘 استكشاف الأخطاء

### المشكلة: Webhook لا يستجيب

- ✅ تأكد أن Render Service شغال
- ✅ تأكد من صحة `VERIFY_TOKEN`
- ✅ شوف الـ Logs في Render

### المشكلة: البوت لا يرد

- ✅ تأكد من `PAGE_ACCESS_TOKEN`
- ✅ تأكد من `GROQ_API_KEY`
- ✅ شوف الـ Logs

### المشكلة: التعليقات لا تعمل

- ✅ تأكد من Subscription للـ `feed`
- ✅ تأكد من Permissions

---

## 📞 الدعم

للمساعدة، تواصل معي أو راجع:

- [Facebook Messenger Platform Docs](https://developers.facebook.com/docs/messenger-platform)
- [Render Docs](https://render.com/docs)

---

**بالتوفيق! 🚀**
