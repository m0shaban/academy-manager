# Google Sheets CMS + Telegram Uploader + 30min Buffer (Human-in-the-Loop)

هذا الدليل يشرح إعداد نظامك بحيث تكون **Google Sheets هي قاعدة البيانات المركزية (CMS)**.

الفكرة:

- ترسل صور على Telegram (من حساب الأدمن فقط)
- النظام يرفع الصورة + يولد Caption بالذكاء الاصطناعي
- **لا ينشر فوراً** → يتم وضعها في **Buffer لمدة 30 دقيقة** داخل Google Sheet
- يمكنك تعديل الكابشن أو النشر فوراً من Streamlit
- الناشر (Publisher) يفحص الشيت كل دقيقة وينشر أي شيء أصبح موعده مستحقاً

---

## 1) ملفات المشروع المهمة

- `webhook.py`: سيرفر Render (Facebook posting + Publisher tick + APIs)
- `app.py`: Streamlit Dashboard (إدارة المحتوى + Pending Posts من الشيت)
- `telegram_bot.py`: Telegram Uploader (يستقبل الصور ويضيفها للشيت)
- `gsheets_cms.py`: طبقة التعامل مع Google Sheets (قراءة/كتابة/Backoff)
- `main.py`: سكربت اختياري لتشغيل Publisher tick كل دقيقة (بديل للكرون)

---

## 2) تجهيز Google Sheet (قاعدة البيانات)

### 2.1 إنشاء Sheet

- أنشئ Google Sheet جديدة
- أنشئ Worksheet (Tab) باسم: `Buffer` (أو اسم آخر)

### 2.2 الأعمدة المطلوبة (Header)

ضع في الصف الأول بالترتيب التالي (بالضبط):

- `Timestamp`
- `Image_URL`
- `AI_Caption`
- `Status`
- `Scheduled_Time`

**Status values**:

- `Scheduled` (جاهز وينتظر الموعد)
- `Posted` (تم النشر)
- `Failed` (فشل النشر)
- `Cancelled` (إلغاء من الداشبورد)

> لو الـ Header مش موجود، النظام سيحاول إضافته تلقائياً.

---

## 3) إعداد Google Service Account

### 3.1 إنشاء Service Account + Key

1. افتح Google Cloud Console
2. أنشئ Project أو استخدم Project موجود
3. اذهب إلى: IAM & Admin → Service Accounts
4. Create Service Account
5. Keys → Add Key → Create new key → JSON
6. احفظ الـ JSON

### 3.2 مشاركة الشيت مع الـ Service Account

- افتح Google Sheet
- Share
- أضف البريد الإلكتروني الخاص بالـ Service Account (داخل JSON عند `client_email`)
- اعطه صلاحية **Editor**

---

## 4) إعداد Render (خدمة webhook)

### 4.1 Dependencies

Render يبني المشروع باستخدام:

- `requirements-webhook.txt`

### 4.2 متغيرات البيئة (Environment Variables)

في Render (Service: `academy-webhook`) اضف:

**Facebook/AI**

- `PAGE_ACCESS_TOKEN`
- `GROQ_API_KEY_4`

**Security**

- `CRON_SECRET` (سر قوي – مهم جداً)
- `ADMIN_TOKEN` (سر قوي – لحماية endpoints الإدارية)
- `VERIFY_TOKEN` (اختياري لو بتستخدم Meta Webhook verify)

**Google Sheets CMS**

- `GOOGLE_SHEET_ID` (ID الشيت)
- `GOOGLE_SHEET_WORKSHEET` (مثلاً: `Buffer`)
- `GOOGLE_SERVICE_ACCOUNT_JSON` (ضع JSON كامل كسطر واحد)

**Landing**

- `DASHBOARD_URL` (لينك Streamlit)

> ملاحظة: لو JSON فيه سطور جديدة، الأفضل تحويله إلى سطر واحد قبل وضعه في Render.

---

## 5) إعداد Streamlit Dashboard (Secrets)

في Streamlit Cloud → App Settings → Secrets أضف:

```toml
BACKEND_URL = "https://<your-render-app>.onrender.com"
ADMIN_TOKEN = "<same as Render ADMIN_TOKEN>"
PAGE_ACCESS_TOKEN = "<your page token>"
GOOGLE_SHEET_ID = "<sheet id>"
GOOGLE_SHEET_WORKSHEET = "Buffer"

[gcp_service_account]
# انسخ محتوى JSON هنا كحقول TOML (أو كنص JSON حسب إعدادك)
# أسهل طريقة: حوّل JSON إلى TOML fields بنفس المفاتيح
# مثال مختصر:
# type = "service_account"
# project_id = "..."
# private_key_id = "..."
# private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
# client_email = "..."
# client_id = "..."
```

داخل الداشبورد ستجد قسم:

- **Pending Posts (Google Sheets CMS)**

وفيه:

- Save/Update لتعديل الكابشن
- Post Now للنشر الفوري
- Delete لإلغاء الصف (يحوّل Status إلى Cancelled)

---

## 6) إعداد Telegram Bot (Uploader)

### 6.1 المتطلبات

- ملف التشغيل: `telegram_bot.py`
- Dependences: `requirements-telegram.txt`

### 6.2 Environment Variables للبوت

ضع هذه المتغيرات حيث ستشغل البوت:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_ID` (رقم حسابك على تيليجرام)
- `IMGBB_API_KEY`
- `GROQ_API_KEY_4`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SHEET_WORKSHEET` (مثلاً Buffer)
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `BUFFER_MINUTES` (افتراضي 30)

### 6.3 تشغيل البوت محلياً (اختبار)

```bash
pip install -r requirements-telegram.txt
python telegram_bot.py
```

ثم ارسل صورة للبوت من حساب الأدمن.

النتيجة المتوقعة:

- يرد عليك: Saved to queue
- ويتم إضافة صف جديد في الشيت بـ Status = Scheduled و Scheduled_Time بعد 30 دقيقة

---

## 7) تشغيل الناشر Publisher كل دقيقة

هناك طريقتين:

### الطريقة A (مفضلة): Cron / UptimeRobot على Render endpoint

نداء كل دقيقة:

`GET https://<render-app>.onrender.com/publisher-tick?secret=<CRON_SECRET>`

- سيقوم بنشر أي صف Scheduled أصبح موعده مستحق
- لو لا يوجد مستحق، يعمل fallback للنشر العشوائي داخل الساعات النشطة

### الطريقة B: تشغيل `main.py` كـ Worker

لو ستشغل Worker دائم:

```bash
python main.py
```

ويحتاج:

- `BACKEND_URL`
- `CRON_SECRET`

---

## 8) Testing سريع (Checklist)

1. تأكد أن الشيت متشارك مع service account
2. أرسل صورة من تيليجرام → تحقق أن الصف اتضاف في الشيت
3. افتح Streamlit → Pending Posts → عدّل الكابشن واضغط Save
4. جرّب Post Now من الداشبورد
5. جرّب publisher tick يدوياً:
   - افتح في المتصفح: `/publisher-tick?secret=...`
6. راقب `/status` لمعرفة هل فيه نشر حديث:
   - `last_facebook_post_at`
   - `last_facebook_post_id`

---

## 9) Troubleshooting

- **الشيت لا يتحدث / Permission denied**
  - شارك الشيت مع `client_email` من service account
  - تأكد أن GOOGLE_SERVICE_ACCOUNT_JSON صحيح

- **النشر يفشل**
  - تأكد `PAGE_ACCESS_TOKEN` صالح وبصلاحيات Page
  - راجع logs في Render لمعرفة رسالة الخطأ

- **Telegram bot لا يرد**
  - تأكد `TELEGRAM_BOT_TOKEN`
  - تأكد `TELEGRAM_ADMIN_ID` هو حسابك الصحيح

- **Rate limits**
  - الطبقة `gsheets_cms.py` تستخدم backoff تلقائي
  - قلل عدد العمليات أو زد interval

---

## 10) Security Notes

- لا تضع أسرار في Git.
- استخدم `ADMIN_TOKEN` و `CRON_SECRET` قيم قوية وطويلة.
- لا تشارك Service Account JSON مع أي شخص.
