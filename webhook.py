from flask import Flask, request, jsonify
import os
import sqlite3
import random
from datetime import datetime, timedelta

from groq import Groq
import requests
import feedparser
from bs4 import BeautifulSoup
import pytz

app = Flask(__name__)

# API Keys from environment
GROQ_API_KEY = os.environ.get("GROQ_API_KEY_4")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = "academy_webhook_2026"
CRON_SECRET = "my_secret_cron_key_123"  # حماية للرابط عشان محدش غيرك يشغله

# Initialize Groq
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# SQLite DB for SaaS (subscriptions + vouchers)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "saas.db")


def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            subscription_end TEXT,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vouchers (
            code TEXT PRIMARY KEY,
            duration_days INTEGER NOT NULL,
            is_used INTEGER DEFAULT 0,
            used_by TEXT,
            used_at TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


init_db()

# الثوابت والصور
FALLBACK_IMAGES = [
    "https://i.ibb.co/xKGpF5sQ/469991854-122136396014386621-3832266993418146234-n.jpg",  # Captain Ezz
    "https://images.unsplash.com/photo-1555597673-b21d5c935865?fm=jpg",  # Karate Kid
    "https://images.unsplash.com/photo-1516684991026-4c3032a2b4fd?fm=jpg",  # Martial Arts Training
    "https://images.unsplash.com/photo-1607031767898-5f319512ff1e?fm=jpg",  # Taekwondo Kick
    "https://images.unsplash.com/photo-1738835935023-ebff4a85bc7e?fm=jpg",  # Kung Fu Pose
    "https://images.unsplash.com/photo-1617627590804-1de3424fbf04?fm=jpg",  # Boxing Gloves
    "https://images.unsplash.com/photo-1764622078672-20f2cf5fcbc1?fm=jpg",  # Gymnastics Balance
    "https://images.unsplash.com/photo-1711825044889-371d0cdf5fe1?fm=jpg",  # Focus & Discipline
    "https://images.unsplash.com/photo-1699464676033-150f72c9f030?fm=jpg",  # Group Training
    "https://images.unsplash.com/photo-1616447285757-3d0084ebd43b?fm=jpg",  # Fitness
    "https://images.unsplash.com/photo-1764622078439-245a43822a5c?fm=jpg",  # Active Kids
]

# RSS Feeds for Sports & Health Content
RSS_FEEDS = [
    # Karate
    "https://feeds.feedburner.com/karatemart",
    "https://kaizenfitnessusa.com/blog?format=rss",
    "https://karateoc.com/feed",
    "https://www.karatebyjesse.com/feed/",
    # Kung Fu & Martial Arts General
    "https://kungfu.kids/blog/feed",
    "https://smabloggers.com/tag/kung-fu/feed",
    "https://blackbeltmag.com/feed",
    "https://ymaa.com/publishing/articles/feed",
    "https://blog.centuryma.com/rss.xml",
    "https://martialartsteachers.com/feed/",
    # Kickboxing & MMA
    "https://sidekickboxing.co.uk/blog/feed/",
    "https://www.ufcgym.com.au/fitness-blog/rss",
    "https://fightcamp.com/blog/rss/",
    "https://www.bjjee.com/feed/",
    # Gymnastics
    "https://shiftmovementscience.com/feed/",
    "https://usagym.org/feed/",
    "https://mountain-kids.com/feed/",
    "https://gymnasticscoaching.com/feed/",
    "https://insidegymnastics.com/feed/",
    # Taekwondo & Judo
    "https://taekwondonation.com/feed/",
    "https://illinoistkd.com/feed/",
    "http://usnta.net/category/blog/feed/",
    "https://tkdlifemagazine.com/feed/",
    "https://judocrazy.com/feed/",
    # Parenting & Kids Fitness
    "https://activeforlife.com/feed/",
    "https://changingthegameproject.com/feed/",
    "https://breakingmuscle.com/feed/",
    # General & Local
    "https://www.skysewsports.com/rss",
    "https://feeds.feedburner.com/AceFitFacts",
    "https://www.youm7.com/rss/SectionRss?SectionID=298",
]

# Academy Data
ACADEMY_DATA = {
    "academy_name": "أكاديمية أبطال أكتوبر",
    "manager": "كابتن عز غريب",
    "phone": "01004945997",
    "phone_alt": "01033111786",
    "location": "الحي الثاني، المجاورة السابعة، عمارة 2151، مدينة 6 أكتوبر",
    "map_link": "https://maps.app.goo.gl/LLN1UTGfgcaFihqL8",
    "facebook": "https://www.facebook.com/october.heroes.academy",
    "schedules": {
        "كاراتيه": ["الأحد والثلاثاء والخميس - 4:30 م"],
        "كونغ فو": ["الاثنين والأربعاء - 6:00 م"],
        "كيك بوكسينج": ["الأحد والثلاثاء والأربعاء - 7:30 م"],
        "جمباز": ["الاثنين والخميس - 3:00 م (مبتدئين)", "الاثنين والخميس - 5:30 م"],
        "ملاكمة": ["بالاتفاق مع الكابتن"],
        "تايكوندو": ["بالاتفاق مع الكابتن"],
    },
    "pricing": {
        "كاراتيه": "500 جنيه/شهر",
        "كونغ فو": "500 جنيه/شهر",
        "كيك بوكسينج": "500 جنيه/شهر",
        "جمباز": "600 جنيه/شهر",
        "تايكوندو": "600 جنيه/شهر",
        "ملاكمة": "600 جنيه/شهر",
    },
    "offers": [
        "🎉 بمناسبة العام الجديد - بادر بالحجز لفترة محدودة!",
        "💪 اشتراك شهري للكاراتيه والكونغ فو والكيك بوكس 500 جنيه فقط!",
        "🤸 الجمباز والتايكوندو والملاكمة 600 جنيه لفترة محدودة!",
    ],
}

# Configuration Defaults (قابل للتعديل من التطبيق)
BOT_CONFIG = {
    "system_prompt_mood": "حماسي جداً",
    "active_hours": [9, 11, 14, 17, 20, 22],
    "rss_feeds": RSS_FEEDS,
}

# ذاكرة مؤقتة لمنع التكرار في نفس الساعة
LAST_POST_HOUR_KEY = None


# ============ SaaS Helpers ============
def _generate_code(length=12):
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(random.choice(alphabet) for _ in range(length))


def generate_vouchers(count=20, duration_days=30):
    now = datetime.utcnow().isoformat()
    codes = []
    conn = get_db()
    cur = conn.cursor()
    for _ in range(count):
        code = _generate_code()
        codes.append(code)
        cur.execute(
            "INSERT OR IGNORE INTO vouchers (code, duration_days, created_at) VALUES (?, ?, ?)",
            (code, duration_days, now),
        )
    conn.commit()
    conn.close()
    return codes


def activate_voucher(user_id: str, voucher_code: str):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT duration_days, is_used FROM vouchers WHERE code = ?",
        (voucher_code,),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, "❌ الكود غير صحيح"

    duration_days, is_used = row
    if is_used:
        conn.close()
        return False, "⚠️ الكود مستخدم مسبقاً"

    expiry = datetime.utcnow() + timedelta(days=duration_days)
    expiry_str = expiry.isoformat()
    now = datetime.utcnow().isoformat()

    # Upsert user
    cur.execute(
        "INSERT OR REPLACE INTO users (user_id, subscription_end, created_at) VALUES (?, ?, COALESCE((SELECT created_at FROM users WHERE user_id = ?), ?))",
        (user_id, expiry_str, user_id, now),
    )

    # Mark voucher used
    cur.execute(
        "UPDATE vouchers SET is_used = 1, used_by = ?, used_at = ? WHERE code = ?",
        (user_id, now, voucher_code),
    )

    conn.commit()
    conn.close()
    return True, expiry_str


def is_premium(user_id: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT subscription_end FROM users WHERE user_id = ?",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return False
    try:
        expiry = datetime.fromisoformat(row[0])
        return expiry > datetime.utcnow()
    except Exception:
        return False


def get_mood_prompt(mood):
    if mood == "رسمي جداً":
        return "أسلوبك رسمي، مهني، ومختصر. استخدم 'حضرتك' و'يا فندم'."
    elif mood == "متوازن":
        return "أسلوبك ودود ومحترم، بين الرسمية والصداقة."
    else:  # حماسي
        return (
            "أسلوبك كابتن رياضي، كلك طاقة، استخدم 'يا بطل' و'يا وحش' وكتير من الإيموجي."
        )


SYSTEM_PROMPT_BASE = """أنت "كابتن عز غريب"، صانع محتوى رياضي ومدرب خبير.
الهدف: تقديم قيمة حقيقية، تحفيز الناس، والتسويق للأكاديمية بذكاء.
"""


def get_cairo_time():
    """Get current time in Cairo"""
    cairo_tz = pytz.timezone("Africa/Cairo")
    return datetime.now(cairo_tz)


def extract_image_from_url(url):
    """Attempt to extract the main image from a webpage/article"""
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")

        # Try og:image
        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            return og_image["content"]

        # Try twitter:image
        twitter_image = soup.find("meta", name="twitter:image")
        if twitter_image and twitter_image.get("content"):
            return twitter_image["content"]

        return None
    except:
        return None


def fetch_content_idea():
    """Fetch an idea from RSS or generate a topic based on time of day"""
    current_hour = get_cairo_time().hour

    # تحديد نوع المنشور حسب الوقت
    post_type = "general"
    if 8 <= current_hour < 11:
        post_type = "motivation_morning"  # صباح وتفاؤل
    elif 11 <= current_hour < 14:
        post_type = "health_tip"  # نصيحة في وسط اليوم
    elif 14 <= current_hour < 17:
        post_type = "kids_advice"  # نصيحة للأمهات والأطفال بعد المدرسة
    elif 17 <= current_hour < 20:
        post_type = "training_drill"  # وقت التمرين
    elif 20 <= current_hour <= 23:
        post_type = "academy_offer"  # عرض مباشر للحجز

    # تفضيل احضار محتوى خارجي للتعليق عليه (Curated Content)
    try:
        # استخدام القائمة من الكونفيج
        feeds_list = BOT_CONFIG.get("rss_feeds", RSS_FEEDS)

        if random.choice([True, False]):  # 50% فرصة لجلب محتوى خارجي
            feed = feedparser.parse(random.choice(feeds_list))
            if feed.entries:
                entry = random.choice(feed.entries[:5])
                image_url = extract_image_from_url(entry.link)
                return {
                    "type": "curated",
                    "title": entry.title,
                    "link": entry.link,
                    "summary": entry.get("summary", ""),
                    "image_url": image_url,
                }
    except:
        pass

    # لو فشل ال RSS، ارجع لإنشاء محتوى أصلي
    return {
        "type": "original",
        "category": post_type,
        "image_url": random.choice(FALLBACK_IMAGES),
    }


def generate_social_post(idea):
    """Generate the post text using Groq"""

    if idea["type"] == "curated":
        prompt = f"""
        أنت كابتن عز غريب.
        {get_mood_prompt(BOT_CONFIG['system_prompt_mood'])}
        
        لقيت المقال ده عن الرياضة:
        العنوان: {idea['title']}
        الملخص: {idea['summary']}
        
        اكتب بوست فيسبوك تعلق فيه على الموضوع ده.
        1. ابدأ بجملة تشد الانتباه (Hook).
        2. لخص الفكرة المهمة باختصار وبالعامية المصرية.
        3. ضيف نصيحة إضافية من عندك "تكة الكابتن".
        4. (اختياري) لو مناسب، اربط الموضوع برياضة موجودة في الأكاديمية عندنا.
        5. لا تذكر الرابط، فقط علق على المحتوى.
        """
    else:
        topics = {
            "motivation_morning": "بوست صباحي تحفيزي عن النشاط والبداية القوية.",
            "health_tip": "نصيحة تغذية أو شرب مياه أو نوم للرياضيين.",
            "kids_advice": "نصيحة لأولياء الأمور عن التعامل مع طاقة الأطفال وتوجيهها للرياضة.",
            "training_drill": "معلومة فنية بسيطة عن الكاراتيه أو الجمباز أو الكونفو.",
            "academy_offer": "بوست دعائي مباشر بس بأسلوب 'خايف على مصلحتك'.. الحق مكانك في عروض السنة الجديدة.",
        }
        topic_desc = topics.get(idea["category"], "نصيحة رياضية عامة")

        prompt = f"""
        أنت كابتن عز غريب.
        {get_mood_prompt(BOT_CONFIG['system_prompt_mood'])}

        اكتب بوست فيسبوك عن: {topic_desc}
        
        الأسلوب:
        - عامية مصرية.
        - استخدم إيموجي مناسبة 🥊🥋💪.
        - خلي الكلام مقسم فقرات قصيرة (سهل القراءة).
        - اختم بـ Call to Action (سؤال للمتابعين، أو دعوة للتمرين).
        """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT_BASE
                    + f"\nبيانات الأكاديمية: {ACADEMY_DATA}",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.8,
        )
        return response.choices[0].message.content
    except:
        return None


def publish_to_facebook(message, image_url=None):
    """Publish content to Facebook Page"""
    if not PAGE_ACCESS_TOKEN:
        return "No Page Access Token Configured"

    url = f"https://graph.facebook.com/v18.0/me/feed"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"message": message}

    if image_url:
        data["link"] = image_url

    try:
        requests.post(url, params=params, json=data, timeout=30)
        return "Published Successfully"
    except Exception as e:
        return f"Error publishing: {e}"


def generate_response(message):
    """Generate AI response using Groq"""
    if not client:
        return "عذراً، حدث خطأ مؤقت. للتواصل: 01004945997 أو 01033111786"

    phones = f"{ACADEMY_DATA['phone']} أو {ACADEMY_DATA['phone_alt']}"

    context = f"""
📍 معلومات الأكاديمية:
- الاسم: {ACADEMY_DATA['academy_name']}
- المدير: {ACADEMY_DATA['manager']}
- العنوان: {ACADEMY_DATA['location']}
- خريطة جوجل: {ACADEMY_DATA['map_link']}
- فيسبوك: {ACADEMY_DATA['facebook']}
- الهاتف: {phones}

📅 المواعيد:
"""

    for sport, times in ACADEMY_DATA["schedules"].items():
        context += f"\n- {sport}: {', '.join(times)}"

    context += "\n\n💰 الأسعار:\n"
    for sport, price in ACADEMY_DATA["pricing"].items():
        context += f"- {sport}: {price}\n"

    context += "\n🎁 العروض الحالية:\n"
    for offer in ACADEMY_DATA["offers"]:
        context += f"- {offer}\n"

    mood_prompt = get_mood_prompt(BOT_CONFIG.get("system_prompt_mood", "حماسي جداً"))
    full_system_prompt = f"{SYSTEM_PROMPT_BASE}\n{mood_prompt}\n\n{context}"

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": message},
            ],
            max_tokens=800,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error generating response: {e}")
        return f"أهلاً! 🥋\n\nللاستفسار عن الأكاديمية، تواصل معنا:\n📞 {phones}\n📍 {ACADEMY_DATA['location']}"


def send_message(recipient_id, message_text):
    """Send message via Facebook Messenger API"""
    if not PAGE_ACCESS_TOKEN:
        print("Error: PAGE_ACCESS_TOKEN not set")
        return

    url = "https://graph.facebook.com/v18.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}

    try:
        response = requests.post(url, params=params, json=data, timeout=10)
        response.raise_for_status()
        print(f"✅ Message sent to {recipient_id}")
    except Exception as e:
        print(f"❌ Error sending message: {e}")


def reply_to_comment(comment_id, message):
    """Reply to a Facebook comment"""
    if not PAGE_ACCESS_TOKEN:
        print("Error: PAGE_ACCESS_TOKEN not set")
        return

    url = f"https://graph.facebook.com/v18.0/{comment_id}/comments"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"message": message}

    try:
        response = requests.post(url, params=params, json=data, timeout=10)
        response.raise_for_status()
        print(f"✅ Comment reply sent to {comment_id}")
    except Exception as e:
        print(f"❌ Error replying to comment: {e}")


@app.route("/")
def home():
    """Health check endpoint"""
    return jsonify(
        {"status": "running", "service": "Academy Manager Webhook", "version": "1.0"}
    )


@app.route("/status", methods=["GET"])
def bot_status():
    """Return bot status and configuration"""
    cairo_now = get_cairo_time()
    return jsonify(
        {
            "status": "online",
            "time_cairo": str(cairo_now.strftime("%Y-%m-%d %H:%M:%S")),
            "active_hours": BOT_CONFIG.get("active_hours", []),
            "mood": BOT_CONFIG.get("system_prompt_mood", "Unknown"),
            "last_post_hour": LAST_POST_HOUR_KEY if LAST_POST_HOUR_KEY else "None",
            "rss_count": len(BOT_CONFIG.get("rss_feeds", [])),
        }
    )


@app.route("/update-config", methods=["POST"])
def update_config():
    """Update Bot Configuration from App"""
    global BOT_CONFIG

    # Check Secret
    secret = request.args.get("secret")
    if secret != CRON_SECRET:
        return "Unauthorized", 401

    data = request.get_json()
    if not data:
        return "No data provided", 400

    # Update Config
    if "active_hours" in data:
        BOT_CONFIG["active_hours"] = data["active_hours"]
    if "mood" in data:
        BOT_CONFIG["system_prompt_mood"] = data["mood"]
    if "rss_feeds" in data:
        BOT_CONFIG["rss_feeds"] = data["rss_feeds"]
        global RSS_FEEDS
        RSS_FEEDS = data["rss_feeds"]  # Update the global RSS list too

    return jsonify({"status": "updated", "config": BOT_CONFIG})


@app.route("/gen-vouchers", methods=["POST"])
def gen_vouchers():
    secret = request.args.get("secret")
    if secret != CRON_SECRET:
        return "Unauthorized", 401

    data = request.get_json() or {}
    count = int(data.get("count", 20))
    duration = int(data.get("duration_days", 30))

    codes = generate_vouchers(count=count, duration_days=duration)
    return jsonify({"status": "ok", "count": len(codes), "duration_days": duration, "codes": codes})


@app.route("/activate", methods=["POST"])
def activate_subscription_route():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    voucher_code = data.get("code")

    if not user_id or not voucher_code:
        return jsonify({"status": "error", "message": "user_id و code مطلوبان"}), 400

    ok, result = activate_voucher(user_id, voucher_code)
    if ok:
        return jsonify({"status": "activated", "subscription_end": result})
    return jsonify({"status": "error", "message": result}), 400


@app.route("/subscription-status", methods=["GET"])
def subscription_status():
    user_id = request.args.get("user_id")
    secret = request.args.get("secret")

    if secret and secret != CRON_SECRET:
        return "Unauthorized", 401

    if not user_id:
        return jsonify({"status": "error", "message": "user_id مطلوب"}), 400

    active = is_premium(user_id)

    # Fetch expiry
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT subscription_end FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    expiry = row[0] if row and row[0] else None

    return jsonify({"status": "active" if active else "expired", "active": active, "subscription_end": expiry})


@app.route("/auto-post-trigger", methods=["GET", "POST"])
def auto_scheduler():
    """
    هذا الرابط يتم استدعاؤه بواسطة خدمة Cron Job خارجية
    للنشر التلقائي في المواعيد المحددة
    """
    # 1. Security Check
    secret = request.args.get("secret")
    if secret != CRON_SECRET:
        return "Unauthorized", 401

    # 2. Time Check (Configurable)
    cairo_now = get_cairo_time()
    current_hour_key = cairo_now.strftime("%Y-%m-%d-%H")

    global LAST_POST_HOUR_KEY

    # التحقق هل الساعة الحالية موجودة في الساعات النشطة؟
    is_active_time = False
    if cairo_now.hour in BOT_CONFIG["active_hours"]:
        is_active_time = True

    if not is_active_time:
        return (
            f"Not an active hour (Current: {cairo_now.hour}). Active: {BOT_CONFIG['active_hours']}",
            200,
        )

    # منع التكرار: لو نشرنا بالفعل في هذه الساعة، لا تنشر مرة أخرى
    if LAST_POST_HOUR_KEY == current_hour_key:
        return f"Already posted this hour ({current_hour_key}). Skipping.", 200

    # 3. Generate Content
    idea = fetch_content_idea()
    post_text = generate_social_post(idea)

    if post_text:
        # 4. Publish
        result = publish_to_facebook(post_text, idea.get("image_url"))

        # تحديث وقت آخر نشر بعد النجاح
        if "Successfully" in str(result) or "id" in str(result):
            LAST_POST_HOUR_KEY = current_hour_key

        return jsonify(
            {
                "status": "success",
                "time": str(cairo_now),
                "type": idea.get("type"),
                "result": result,
            }
        )

    return "Failed to generate content", 500


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Webhook verification for Facebook"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified successfully!")
        return challenge, 200
    else:
        print("❌ Webhook verification failed")
        return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """Handle incoming Facebook webhooks"""
    data = request.get_json()

    print(f"📨 Received webhook: {data}")

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            # Handle Messenger Messages
            for messaging in entry.get("messaging", []):
                sender_id = messaging["sender"]["id"]

                if "message" in messaging and "text" in messaging["message"]:
                    message_text = messaging["message"]["text"]
                    print(f"💬 Message from {sender_id}: {message_text}")

                    # Generate response
                    response = generate_response(message_text)

                    # Send back
                    send_message(sender_id, response)

            # Handle Comments
            for change in entry.get("changes", []):
                if change.get("field") == "feed":
                    value = change.get("value", {})

                    # Only reply to NEW comments (add)
                    if value.get("verb") != "add":
                        continue

                    if value.get("item") == "comment":
                        comment_id = value.get("comment_id")
                        message = value.get("message", "")
                        sender_id = value.get("from", {}).get("id")

                        # Print debug info
                        print(f"DEBUG: Processing comment from {sender_id}: {message}")

                        # Generate response
                        response = generate_response(message)

                        # Reply to comment
                        if response:
                             reply_to_comment(comment_id, response)
                        else:
                             print("❌ Failed to generate response for comment")

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
