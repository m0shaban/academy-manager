# WhatsApp API + Facebook Comments Setup Guide
# دليل إعداد WhatsApp و إدارة التعليقات

## Overview
نظام متكامل لاستقبال الرسائل من WhatsApp والتعليقات من Facebook والرد عليها من لوحة تحكم واحدة.

---

## 1️⃣ إعداد Meta App (Facebook/WhatsApp)

### الخطوة 1: إنشء تطبيق على Meta
1. اذهب إلى [Meta Developers](https://developers.facebook.com/)
2. اضغط **My Apps** → **Create App**
3. اختر **Business** → **Next**
4. ملء البيانات:
   - **App Name**: `Academy Manager`
   - **App Contact Email**: بريدك
   - **App Purpose**: Marketing/Communication

### الخطوة 2: إضافة WhatsApp Product
1. في Dashboard، اضغط **+ Add Product**
2. ابحث عن **WhatsApp** واضغط **Set Up**
3. اختر **WhatsApp Business Account** (أو أنشئ جديد)

### الخطوة 3: الحصول على Access Token
1. في WhatsApp Settings، اضغط **API Setup**
2. اختر رقم الهاتف الخاص بك (مثال: +201234567890)
3. انسخ **Phone Number ID**
4. اذهب إلى **System User** وأنشئ Permanent Access Token:
   - اضغط **Tokens** → **Generate Token**
   - اختر الصلاحيات: `whatsapp_business_messaging`, `whatsapp_business_management`
   - انسخ الـ Token

### الخطوة 4: إضافة Facebook App (للتعليقات)
1. في نفس الـ App، اضغط **+ Add Product**
2. ابحث عن **Facebook Login** واضغط **Set Up**
3. في **Settings** → **Basic**، انسخ:
   - **App ID**
   - **App Secret**

---

## 2️⃣ Streamlit Secrets Configuration

في Streamlit Cloud أو محليًا (`.streamlit/secrets.toml`):

```toml
# WhatsApp Integration
WHATSAPP_API_TOKEN = "your_permanent_access_token"
WHATSAPP_PHONE_ID = "your_phone_number_id"
WHATSAPP_VERIFY_TOKEN = "academy_whatsapp_2026"

# Facebook Page Token
PAGE_ACCESS_TOKEN = "your_facebook_page_access_token"

# Admin Protection
ADMIN_TOKEN = "your_secure_admin_token"

# Backend URL
BACKEND_URL = "https://your-render-app.onrender.com"
```

---

## 3️⃣ Render Environment Setup

في Render Dashboard → **Environment**، أضف:

```bash
WHATSAPP_API_TOKEN=your_permanent_access_token
WHATSAPP_PHONE_ID=your_phone_number_id
WHATSAPP_VERIFY_TOKEN=academy_whatsapp_2026
PAGE_ACCESS_TOKEN=your_facebook_page_access_token
ADMIN_TOKEN=your_secure_admin_token
```

---

## 4️⃣ Webhook Configuration (في Meta App)

### WhatsApp Webhook
1. في WhatsApp Settings → **Configuration**
2. **Callback URL**: `https://your-app.onrender.com/whatsapp/webhook`
3. **Verify Token**: `academy_whatsapp_2026`
4. **Subscriptions**: اختر `messages`
5. اضغط **Verify and Save**

### Facebook Comments Webhook
1. في Facebook App Settings → **Webhooks**
2. **Callback URL**: `https://your-app.onrender.com/facebook/comments`
3. **Verify Token**: `academy_webhook_2026`
4. **Subscriptions**: اختر `feed`, `comments`
5. اضغط **Verify and Save**

---

## 5️⃣ API Endpoints Reference

### Receive WhatsApp Messages
```
POST /whatsapp/webhook
```
- يستقبل الرسائل تلقائيًا من WhatsApp
- يحفظها في قاعدة البيانات

### Send WhatsApp Message
```
POST /whatsapp/send
Headers: X-Admin-Token: your_admin_token
Body: {
  "phone": "+201234567890",
  "message": "مرحباً! هل تريد الاشتراك؟"
}
```

### List All Messages
```
GET /messages/list
Headers: X-Admin-Token: your_admin_token
```
Response:
```json
{
  "items": [
    {
      "id": 1,
      "type": "message",
      "platform": "whatsapp",
      "sender": "Ahmed",
      "content": "Hello",
      "received_at": "2026-01-13T10:30:00",
      "status": "pending"
    },
    {
      "id": 2,
      "type": "comment",
      "platform": "facebook",
      "sender": "Sara",
      "content": "Great post!",
      "received_at": "2026-01-13T10:25:00",
      "status": "replied"
    }
  ]
}
```

### Reply to Facebook Comment
```
POST /facebook/comments/reply
Headers: X-Admin-Token: your_admin_token
Body: {
  "comment_id": "123456789",
  "reply": "شكراً على تعليقك! 😊"
}
```

---

## 6️⃣ Streamlit UI

في **Tab 7: الرسائل**، ستجد:

1. **الرسائل المعلقة**: عرض الرسائل التي لم يتم الرد عليها
2. **كل الرسائل**: عرض السجل الكامل
3. **الرد السريع**: اكتب الرد مباشرة في الواجهة
4. **روابط Webhooks**: للنسخ عند الحاجة

---

## 7️⃣ Template Responses (اختياري)

أضف ردود سريعة في `academy_data.json`:

```json
{
  "quick_replies": {
    "welcome": "مرحباً بك في أكاديمية أبطال أكتوبر! 🥋 كيف يمكننا مساعدتك؟",
    "schedule": "مواعيد التدريب:\n- الكاراتيه: الأحد والثلاثاء والخميس 4:30 م\n- الكونغ فو: الاثنين والأربعاء 6:00 م",
    "pricing": "الأسعار:\n- الكاراتيه والكونغ فو والكيك بوكس: 500 جنيه/شهر\n- الجمباز والتايكوندو والملاكمة: 600 جنيه/شهر",
    "location": "العنوان: الحي الثاني، المجاورة السابعة، عمارة 2151، مدينة 6 أكتوبر"
  }
}
```

---

## 8️⃣ Troubleshooting

### ❌ "Unauthorized" عند محاولة إرسال رسالة
- تأكد من `ADMIN_TOKEN` موجود على Render و Streamlit
- تأكد من نفس القيمة بالضبط (بدون مسافات)

### ❌ "Webhook verification failed"
- تأكد من **Verify Token** صحيح في Meta App
- تأكد من رابط Webhook صحيح وتطبيق Render يعمل

### ❌ لا تصل الرسائل
- تأكد من `WHATSAPP_API_TOKEN` و `WHATSAPP_PHONE_ID` صحيح
- تأكد من تفعيل **messages** في WhatsApp Subscriptions

### ❌ التعليقات لا تظهر
- تأكد من `PAGE_ACCESS_TOKEN` يحتوي على صلاحية `pages_read_engagement`
- تأكد من الصفحة لديها تعليقات فعلية

---

## 9️⃣ Testing

### Test WhatsApp
```bash
curl -X POST https://your-app.onrender.com/whatsapp/send \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your_admin_token" \
  -d '{
    "phone": "+201234567890",
    "message": "اختبار 🚀"
  }'
```

### Test Facebook Comments
```bash
curl -X GET https://your-app.onrender.com/messages/list \
  -H "X-Admin-Token: your_admin_token"
```

---

## 🔟 Security Tips

1. **لا تشارك Tokens**: لا تضعها في الكود مباشرة
2. **استخدم ADMIN_TOKEN**: حماية الـ endpoints الحساسة
3. **فعّل HTTPS**: كل الـ webhooks يجب أن تكون HTTPS
4. **راجع الرسائل**: تأكد من الرسائل المرسلة قبل النقر "إرسال"

---

## 📞 Support

للمساعدة:
- تحقق من Meta Developers Documentation
- تأكد من أن الـ Meta App في **Live Mode** وليس Development
- فعّل Webhooks من فترة لفترة للحفاظ على الاتصال نشطًا

---

**Version**: 5.0  
**Last Updated**: Jan 13, 2026  
**Status**: ✅ Production Ready
