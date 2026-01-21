from flask import Flask, request, jsonify, Response
import os
import sqlite3
import random
from datetime import datetime, timedelta
from datetime import timezone
import base64

from groq import Groq
import requests
import feedparser
from bs4 import BeautifulSoup
import pytz

from gsheets_cms import (
    SheetConfig,
    append_scheduled_post,
    ensure_headers,
    find_due_scheduled,
    list_rows,
    load_service_account_info_from_env,
    make_gspread_client,
    open_worksheet,
    update_status,
)

app = Flask(__name__)

# API Keys from environment
GROQ_API_KEY = os.environ.get("GROQ_API_KEY_4")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "academy_webhook_2026")
CRON_SECRET = os.environ.get(
    "CRON_SECRET", "my_secret_cron_key_123"
)  # حماية للرابط عشان محدش غيرك يشغله
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")  # حماية احترافية لتوليد الأكواد (Header)

# WhatsApp API
WHATSAPP_API_TOKEN = os.environ.get("WHATSAPP_API_TOKEN", "")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "academy_whatsapp_2026")

# Google Sheets CMS
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_WORKSHEET = os.environ.get("GOOGLE_SHEET_WORKSHEET", "Buffer")

# Telegram Webhook Uploader (single web server option)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY", "")
BUFFER_MINUTES = int(os.environ.get("BUFFER_MINUTES", "30") or "30")

_GS_CLIENT = None
_GS_WS = None
_GS_HEADER = None


def _get_sheet():
    global _GS_CLIENT, _GS_WS, _GS_HEADER

    if not GOOGLE_SHEET_ID:
        return None, None

    if _GS_WS is not None and _GS_HEADER is not None:
        return _GS_WS, _GS_HEADER

    svc = load_service_account_info_from_env()
    if not svc:
        return None, None

    if _GS_CLIENT is None:
        _GS_CLIENT = make_gspread_client(svc)

    cfg = SheetConfig(sheet_id=GOOGLE_SHEET_ID, worksheet=GOOGLE_SHEET_WORKSHEET)
    ws = open_worksheet(_GS_CLIENT, cfg)
    header = ensure_headers(ws)
    _GS_WS, _GS_HEADER = ws, header
    return ws, header


def _is_publish_success(result: str) -> bool:
    s = str(result or "")
    return "Published Successfully" in s or s.strip().startswith("{") or "id" in s


def _telegram_api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"


def _telegram_send_message(chat_id: int, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(
            _telegram_api_url("sendMessage"),
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
    except Exception:
        pass


def _imgbb_upload(image_bytes: bytes) -> str:
    if not IMGBB_API_KEY:
        return ""

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    try:
        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY, "image": b64},
            timeout=60,
        )
        payload = resp.json() if resp.content else {}
        if resp.status_code != 200:
            return ""
        data = payload.get("data") or {}
        return str(data.get("url") or data.get("display_url") or "").strip()
    except Exception:
        return ""


def _generate_telegram_caption(user_caption: str) -> str:
    user_caption = str(user_caption or "").strip()
    if user_caption:
        return user_caption

    # fallback: use existing post generator style
    try:
        idea = {
            "type": "original",
            "category": "training_drill",
            "image_url": "",
        }
        text = generate_social_post(idea)
        return str(text or "").strip() or "بوست جديد من الأكاديمية 💪"
    except Exception:
        return "بوست جديد من الأكاديمية 💪"


@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    # Security: validate Telegram secret header
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not TELEGRAM_WEBHOOK_SECRET or secret != TELEGRAM_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "unauthorized"}), 403

    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}), 500

    ws, header = _get_sheet()
    if not ws or not header:
        return jsonify({"ok": False, "error": "Google Sheets not configured"}), 500

    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message") or {}

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    from_user = message.get("from") or {}
    from_id = from_user.get("id")

    # Admin-only
    try:
        admin_id = int(str(TELEGRAM_ADMIN_ID).strip()) if TELEGRAM_ADMIN_ID else None
    except Exception:
        admin_id = None

    if admin_id and from_id != admin_id:
        if chat_id:
            _telegram_send_message(chat_id, "غير مسموح. هذا البوت للأدمن فقط.")
        return jsonify({"ok": True})

    photos = message.get("photo") or []
    if not photos:
        if chat_id:
            _telegram_send_message(chat_id, "ابعت صورة فقط.")
        return jsonify({"ok": True})

    # pick largest photo
    best = photos[-1]
    file_id = best.get("file_id")
    if not file_id:
        return jsonify({"ok": True})

    # Download file bytes from Telegram
    try:
        r = requests.get(_telegram_api_url("getFile"), params={"file_id": file_id}, timeout=20)
        payload = r.json() if r.content else {}
        if not payload.get("ok"):
            raise RuntimeError("getFile failed")
        file_path = (payload.get("result") or {}).get("file_path")
        if not file_path:
            raise RuntimeError("no file_path")

        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
        img_resp = requests.get(file_url, timeout=60)
        img_resp.raise_for_status()
        image_bytes = img_resp.content
    except Exception:
        if chat_id:
            _telegram_send_message(chat_id, "حصل خطأ في تحميل الصورة من Telegram.")
        return jsonify({"ok": True})

    image_url = _imgbb_upload(image_bytes)
    if not image_url:
        if chat_id:
            _telegram_send_message(chat_id, "حصل خطأ في رفع الصورة (IMGBB).")
        return jsonify({"ok": True})

    caption_text = _generate_telegram_caption(message.get("caption"))
    scheduled_time = (
        datetime.now(timezone.utc) + timedelta(minutes=max(BUFFER_MINUTES, 0))
    ).replace(microsecond=0)
    scheduled_iso = scheduled_time.isoformat()

    try:
        append_scheduled_post(ws, image_url, caption_text, scheduled_iso)
    except Exception:
        if chat_id:
            _telegram_send_message(chat_id, "حصل خطأ في حفظ البيانات داخل Google Sheet.")
        return jsonify({"ok": True})

    if chat_id:
        _telegram_send_message(
            chat_id,
            f"✅ اتسجلت في الشيت\n⏳ موعد النشر: {scheduled_iso}\n🔗 {image_url}",
        )

    return jsonify({"ok": True, "image_url": image_url, "scheduled_time": scheduled_iso})


def process_due_sheet_posts(max_posts: int = 1) -> dict:
    """Publish due Scheduled posts from Google Sheet.

    Returns summary dict; safe no-op if sheet not configured.
    """
    ws, header = _get_sheet()
    if not ws or not header:
        return {"enabled": False, "posted": 0, "items": []}

    rows = list_rows(ws)
    due = find_due_scheduled(rows, now_utc=datetime.now(timezone.utc))

    posted_items = []
    for item in due[: max_posts or 1]:
        row_number = int(item.get("_row_number"))
        caption = str(item.get("AI_Caption") or "").strip()
        image_url = str(item.get("Image_URL") or "").strip()

        if not caption and not image_url:
            # mark as failed to avoid endless retries
            update_status(ws, row_number, "Failed", header)
            continue

        result = publish_to_facebook(caption, image_url or None)
        if _is_publish_success(result):
            update_status(ws, row_number, "Posted", header)
            posted_items.append(
                {
                    "row": row_number,
                    "status": "Posted",
                    "result": str(result),
                }
            )
        else:
            update_status(ws, row_number, "Failed", header)
            posted_items.append(
                {
                    "row": row_number,
                    "status": "Failed",
                    "result": str(result),
                }
            )

    return {"enabled": True, "posted": len(posted_items), "items": posted_items}


# بسيط ومفيد ضد التخمين (in-memory). مناسب لـ Render single instance.
_GEN_FAILS = {}
_GEN_BLOCKED_UNTIL = {}


def _landing_html(dashboard_url: str) -> str:
    return f"""<!doctype html>
<html lang=\"ar\" dir=\"rtl\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>بوت الأكاديمية • لوحة التعريف</title>
    <style>
        :root {{
            --bg: #0b1220;
            --card: rgba(255,255,255,0.06);
            --card2: rgba(255,255,255,0.10);
            --text: #e6edf6;
            --muted: rgba(230,237,246,0.75);
            --accent: #7c3aed;
            --accent2: #22c55e;
            --border: rgba(255,255,255,0.10);
        }}
        * {{ box-sizing: border-box; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; }}
        body {{ margin: 0; background: radial-gradient(1200px 600px at 20% 10%, rgba(124,58,237,0.25), transparent 50%),
                                         radial-gradient(900px 500px at 80% 0%, rgba(34,197,94,0.20), transparent 55%),
                                         var(--bg);
                     color: var(--text); }}
        .wrap {{ max-width: 1100px; margin: 0 auto; padding: 42px 18px 60px; }}
        .nav {{ display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom: 28px; }}
        .brand {{ display:flex; align-items:center; gap:12px; }}
        .logo {{ width: 44px; height: 44px; border-radius: 14px;
                         background: linear-gradient(135deg, rgba(124,58,237,1), rgba(217,70,239,1));
                         display:flex; align-items:center; justify-content:center; font-weight:900; }}
        .pill {{ padding: 8px 12px; border-radius: 999px; border:1px solid var(--border); background: rgba(255,255,255,0.04); color: var(--muted); font-size: 13px; }}
        .hero {{ display:grid; grid-template-columns: 1.3fr 1fr; gap: 18px; align-items: stretch; }}
        @media (max-width: 900px) {{ .hero {{ grid-template-columns: 1fr; }} }}
        .card {{ border:1px solid var(--border); background: var(--card); border-radius: 22px; padding: 22px; }}
        h1 {{ margin: 0 0 10px 0; font-size: clamp(24px, 4vw, 40px); line-height: 1.25; }}
        p {{ margin: 0 0 14px 0; color: var(--muted); line-height: 1.8; }}
        .cta {{ display:flex; flex-wrap:wrap; gap: 10px; margin-top: 12px; }}
        a.btn {{ text-decoration:none; padding: 12px 16px; border-radius: 14px; font-weight: 700; display:inline-flex; align-items:center; gap:10px; }}
        .primary {{ background: linear-gradient(135deg, rgba(124,58,237,1), rgba(217,70,239,1)); color: #fff; }}
        .secondary {{ background: rgba(255,255,255,0.06); border:1px solid var(--border); color: var(--text); }}
        .grid {{ display:grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 14px; }}
        @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
        .feat {{ padding: 14px; border-radius: 16px; border:1px solid var(--border); background: rgba(255,255,255,0.04); }}
        .feat b {{ display:block; margin-bottom: 6px; }}
        .small {{ font-size: 13px; color: var(--muted); }}
        .footer {{ margin-top: 18px; display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; }}
        code {{ direction:ltr; unicode-bidi: plaintext; background: rgba(0,0,0,0.25); padding: 2px 6px; border-radius: 8px; border:1px solid rgba(255,255,255,0.08); }}
    </style>
</head>
<body>
    <div class=\"wrap\">
        <div class=\"nav\">
            <div class=\"brand\">
                <div class=\"logo\">AI</div>
                <div>
                    <div style=\"font-weight:900; font-size:16px;\">بوت الأكاديمية</div>
                    <div class=\"small\">Business + Technology Landing</div>
                </div>
            </div>
            <div class=\"pill\">Render Webhook Service • Online</div>
        </div>

        <div class=\"hero\">
            <div class=\"card\">
                <h1>خلي البوت يشتغل… وإنت تدير كل حاجة من لوحة التحكم.</h1>
                <p>ده سيرفر الـ <b>Webhook</b> المسؤول عن استقبال الرسائل والأحداث وتشغيل الأتمتة. لو هدفك الإدارة والتعديل والتوليد، افتح لوحة التحكم.</p>
                <div class=\"cta\">
                    <a class=\"btn primary\" href=\"{dashboard_url}\">🚀 دخول لوحة التحكم</a>
                    <a class=\"btn secondary\" href=\"/health\">🟢 فحص الحالة</a>
                </div>
                <div class=\"grid\">
                    <div class=\"feat\"><b>ردود ذكية</b><div class=\"small\">سيناريوهات جاهزة + أسلوب كابتن</div></div>
                    <div class=\"feat\"><b>أتمتة نشر</b><div class=\"small\">تشغيل مهام مجدولة بشكل آمن</div></div>
                    <div class=\"feat\"><b>إدارة من Streamlit</b><div class=\"small\">واجهة عربية، سريعة، وقابلة للتخصيص</div></div>
                </div>
            </div>

            <div class=\"card\" style=\"background: var(--card2);\">
                <h2 style=\"margin:0 0 10px 0;\">للمطور / الأدمن</h2>
                <p class=\"small\">نصائح سريعة:</p>
                <ul class=\"small\" style=\"margin:0; padding-right: 18px; line-height: 1.9;\">
                    <li>لو بتستخدم حماية توليد الأكواد: عرّف <code>ADMIN_TOKEN</code> على Render وStreamlit بنفس القيمة.</li>
                    <li>لو بتراقب الخدمة: استخدم <code>/health</code> بدل ما تستدعي endpoints حساسة.</li>
                    <li>ده مجرد Landing Page — البوت نفسه شغال على endpoints الخلفية.</li>
                </ul>
                <div class=\"footer\">
                    <div class=\"small\">© {datetime.utcnow().year} • Academy Manager</div>
                    <div class=\"small\">Build: Flask + Render</div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""


@app.route("/", methods=["GET"])
def landing_page():
    dashboard_url = os.environ.get("DASHBOARD_URL") or "https://october.streamlit.app/"
    return Response(_landing_html(dashboard_url), mimetype="text/html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "academy-webhook"})


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
    # جداول جديدة للرسائل والتعليقات
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,  -- 'whatsapp' or 'messenger'
            sender_id TEXT,
            sender_name TEXT,
            message_text TEXT,
            received_at TIMESTAMP,
            reply_text TEXT,
            replied_at TIMESTAMP,
            status TEXT  -- 'pending', 'replied'
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comment_id TEXT,
            post_id TEXT,
            sender_id TEXT,
            sender_name TEXT,
            comment_text TEXT,
            received_at TIMESTAMP,
            reply_text TEXT,
            replied_at TIMESTAMP,
            status TEXT  -- 'pending', 'replied'
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP
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
        resp = requests.post(url, params=params, json=data, timeout=30)
        try:
            payload = resp.json()
        except Exception:
            payload = {}

        if resp.status_code != 200:
            return f"Error publishing: {resp.status_code} {payload or resp.text}"

        post_id = payload.get("id")
        if post_id:
            try:
                conn = get_db()
                cur = conn.cursor()
                now = datetime.utcnow().isoformat()
                cur.execute(
                    "INSERT OR REPLACE INTO events (key, value, updated_at) VALUES (?, ?, ?)",
                    ("last_facebook_post_id", str(post_id), now),
                )
                cur.execute(
                    "INSERT OR REPLACE INTO events (key, value, updated_at) VALUES (?, ?, ?)",
                    ("last_facebook_post_at", now, now),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

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
        if response.status_code != 200:
            print(f"❌ Error sending message: {response.status_code} {response.text}")
            return False
        print(f"✅ Message sent to {recipient_id}")
        return True
    except Exception as e:
        print(f"❌ Error sending message: {e}")
        return False


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
        if response.status_code != 200:
            print(
                f"❌ Error replying to comment: {response.status_code} {response.text}"
            )
            return False
        print(f"✅ Comment reply sent to {comment_id}")
        return True
    except Exception as e:
        print(f"❌ Error replying to comment: {e}")
        return False


@app.route("/status", methods=["GET"])
def bot_status():
    """Return bot status and configuration"""
    cairo_now = get_cairo_time()

    last_post_at = None
    last_post_id = None
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT value FROM events WHERE key = ?", ("last_facebook_post_at",)
        )
        row = cur.fetchone()
        last_post_at = row[0] if row else None
        cur.execute(
            "SELECT value FROM events WHERE key = ?", ("last_facebook_post_id",)
        )
        row = cur.fetchone()
        last_post_id = row[0] if row else None
        conn.close()
    except Exception:
        pass

    return jsonify(
        {
            "status": "online",
            "time_cairo": str(cairo_now.strftime("%Y-%m-%d %H:%M:%S")),
            "active_hours": BOT_CONFIG.get("active_hours", []),
            "mood": BOT_CONFIG.get("system_prompt_mood", "Unknown"),
            "last_post_hour": LAST_POST_HOUR_KEY if LAST_POST_HOUR_KEY else "None",
            "last_facebook_post_at": last_post_at,
            "last_facebook_post_id": last_post_id,
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
    """Generate voucher codes (admin-only).

    Professional security: require ADMIN_TOKEN via X-Admin-Token header (if configured).
    UI gates are NOT considered security.
    """
    ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
        or "unknown"
    )
    now_ts = datetime.utcnow().timestamp()

    blocked_until = _GEN_BLOCKED_UNTIL.get(ip)
    if blocked_until and now_ts < blocked_until:
        return jsonify({"status": "error", "message": "تم حظر المحاولات مؤقتاً"}), 429

    data = request.get_json() or {}

    # Preferred: ADMIN_TOKEN header
    if ADMIN_TOKEN:
        provided = request.headers.get("X-Admin-Token", "")
        if not provided or provided != ADMIN_TOKEN:
            # track failures
            window = _GEN_FAILS.get(ip)
            if not window or now_ts - window["first_ts"] > 600:
                window = {"first_ts": now_ts, "count": 0}
            window["count"] += 1
            _GEN_FAILS[ip] = window
            if window["count"] >= 5:
                _GEN_BLOCKED_UNTIL[ip] = now_ts + 1800  # 30 min
            return jsonify({"status": "error", "message": "غير مصرح"}), 403
    else:
        # Legacy fallback (only when ADMIN_TOKEN is not configured)
        step1 = data.get("step1")
        step2 = data.get("step2")
        step3 = data.get("step3")
        if step1 != "بلح" or step2 != "طرح" or step3 != "موز":
            return jsonify({"status": "error", "message": "غير مصرح"}), 401

    count = int(data.get("count", 20))
    duration = int(data.get("duration_days", 30))

    codes = generate_vouchers(count=count, duration_days=duration)
    return jsonify(
        {"status": "ok", "count": len(codes), "duration_days": duration, "codes": codes}
    )


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

    return jsonify(
        {
            "status": "active" if active else "expired",
            "active": active,
            "subscription_end": expiry,
        }
    )


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

    # 2. Always try Google Sheet first (Human-in-the-Loop priority)
    sheet_summary = process_due_sheet_posts(max_posts=1)
    if sheet_summary.get("posted"):
        return jsonify({"status": "sheet_posted", **sheet_summary}), 200

    # 3. Time Check (Configurable)
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

    # 4. Generate Content
    idea = fetch_content_idea()
    post_text = generate_social_post(idea)

    if post_text:
        # 5. Publish
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


@app.route("/publisher-tick", methods=["GET"])
def publisher_tick():
    """Minute-level publisher endpoint.

    Call this every minute (cron/uptimerobot). It will publish due Google-Sheet posts.
    Optionally falls back to random posting only during active hours.
    """
    secret = request.args.get("secret")
    if secret != CRON_SECRET:
        return "Unauthorized", 401

    # 1) Priority: sheet posts
    sheet_summary = process_due_sheet_posts(max_posts=2)
    if sheet_summary.get("posted"):
        return jsonify({"status": "sheet_posted", **sheet_summary}), 200

    # 2) Fallback: hourly random logic (same as auto-post-trigger)
    cairo_now = get_cairo_time()
    current_hour_key = cairo_now.strftime("%Y-%m-%d-%H")
    global LAST_POST_HOUR_KEY

    if cairo_now.hour not in BOT_CONFIG.get("active_hours", []):
        return (
            jsonify(
                {"status": "noop", "reason": "not_active_hour", "time": str(cairo_now)}
            ),
            200,
        )

    if LAST_POST_HOUR_KEY == current_hour_key:
        return (
            jsonify(
                {
                    "status": "noop",
                    "reason": "already_posted_this_hour",
                    "hour": current_hour_key,
                }
            ),
            200,
        )

    idea = fetch_content_idea()
    post_text = generate_social_post(idea)
    if not post_text:
        return (
            jsonify({"status": "error", "message": "Failed to generate content"}),
            500,
        )

    result = publish_to_facebook(post_text, idea.get("image_url"))
    if "Published Successfully" in str(result) or "id" in str(result):
        LAST_POST_HOUR_KEY = current_hour_key

    return (
        jsonify(
            {
                "status": "random_posted",
                "time": str(cairo_now),
                "type": idea.get("type"),
                "result": result,
            }
        ),
        200,
    )


@app.route("/cms/post-now", methods=["POST"])
def cms_post_now():
    """Admin: post a specific Google Sheet row immediately."""
    if ADMIN_TOKEN and request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json() or {}
    row_number = int(payload.get("row_number") or 0)
    if row_number < 2:
        return jsonify({"error": "row_number required"}), 400

    ws, header = _get_sheet()
    if not ws or not header:
        return jsonify({"error": "Google Sheet not configured"}), 500

    # Read row
    values = ws.row_values(row_number)
    item = {
        header[i]: (values[i] if i < len(values) else "") for i in range(len(header))
    }
    caption = str(item.get("AI_Caption") or "").strip()
    image_url = str(item.get("Image_URL") or "").strip()
    if not caption and not image_url:
        update_status(ws, row_number, "Failed", header)
        return jsonify({"error": "Empty row"}), 400

    result = publish_to_facebook(caption, image_url or None)
    if _is_publish_success(result):
        update_status(ws, row_number, "Posted", header)
        return jsonify({"success": True, "result": str(result)}), 200
    update_status(ws, row_number, "Failed", header)
    return jsonify({"success": False, "result": str(result)}), 500


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
                sender_id = (messaging.get("sender") or {}).get("id")
                msg_obj = messaging.get("message")
                if not sender_id or not msg_obj:
                    continue

                # نص الرسالة (قد تكون attachments بدون text)
                if "text" in msg_obj:
                    message_text = msg_obj.get("text") or ""
                elif msg_obj.get("attachments"):
                    message_text = "[attachment]"
                else:
                    message_text = "[message]"

                print(f"💬 Message from {sender_id}: {message_text}")

                # Store in DB (for monitoring/inbox)
                message_id = None
                try:
                    conn = get_db()
                    cur = conn.cursor()
                    now = datetime.utcnow().isoformat()
                    sender_name = f"FB User {str(sender_id)[-4:]}"
                    cur.execute(
                        """
                        INSERT INTO messages (platform, sender_id, sender_name, message_text, received_at, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "messenger",
                            sender_id,
                            sender_name,
                            message_text,
                            now,
                            "pending",
                        ),
                    )
                    message_id = cur.lastrowid
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

                # Generate response (auto-reply)
                response = generate_response(message_text)
                if response:
                    ok = send_message(sender_id, response)
                    if ok and message_id:
                        try:
                            conn = get_db()
                            cur = conn.cursor()
                            cur.execute(
                                "UPDATE messages SET reply_text = ?, replied_at = ?, status = ? WHERE id = ?",
                                (
                                    response,
                                    datetime.utcnow().isoformat(),
                                    "replied",
                                    message_id,
                                ),
                            )
                            conn.commit()
                            conn.close()
                        except Exception:
                            pass

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
                        sender_name = value.get("from", {}).get("name", "Unknown")
                        post_id = value.get("post_id")

                        # Print debug info
                        print(f"DEBUG: Processing comment from {sender_id}: {message}")

                        # Store in DB (avoid duplicates by comment_id when possible)
                        comment_row_id = None
                        if comment_id:
                            try:
                                conn = get_db()
                                cur = conn.cursor()
                                cur.execute(
                                    "SELECT id FROM comments WHERE comment_id = ? LIMIT 1",
                                    (comment_id,),
                                )
                                existing = cur.fetchone()
                                if not existing:
                                    now = datetime.utcnow().isoformat()
                                    cur.execute(
                                        """
                                        INSERT INTO comments (comment_id, post_id, sender_id, sender_name, comment_text, received_at, status)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """,
                                        (
                                            comment_id,
                                            post_id,
                                            sender_id,
                                            sender_name,
                                            message,
                                            now,
                                            "pending",
                                        ),
                                    )
                                    comment_row_id = cur.lastrowid
                                    conn.commit()
                                conn.close()
                            except Exception:
                                pass

                        # Generate response
                        response = generate_response(message)

                        # Reply to comment
                        if response:
                            ok = reply_to_comment(comment_id, response)
                            if ok and comment_id:
                                try:
                                    conn = get_db()
                                    cur = conn.cursor()
                                    cur.execute(
                                        "UPDATE comments SET reply_text = ?, replied_at = ?, status = ? WHERE comment_id = ?",
                                        (
                                            response,
                                            datetime.utcnow().isoformat(),
                                            "replied",
                                            comment_id,
                                        ),
                                    )
                                    conn.commit()
                                    conn.close()
                                except Exception:
                                    pass
                        else:
                            print("❌ Failed to generate response for comment")

    return "OK", 200


# ========================================
# WhatsApp API Endpoints
# ========================================
@app.route("/whatsapp/webhook", methods=["GET"])
def whatsapp_webhook_verify():
    """Verify WhatsApp webhook subscription"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/whatsapp/webhook", methods=["POST"])
def whatsapp_webhook():
    """Receive WhatsApp messages and store in DB"""
    data = request.json

    if not data.get("entry"):
        return jsonify({"status": "ok"}), 200

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "messages":
                messages = change.get("value", {}).get("messages", [])
                contacts = change.get("value", {}).get("contacts", [])

                contact_map = {
                    c["wa_id"]: c.get("profile", {}).get("name", "Unknown")
                    for c in contacts
                }

                for msg in messages:
                    sender_id = msg.get("from")
                    sender_name = contact_map.get(
                        sender_id, f"Customer {sender_id[-4:]}"
                    )
                    message_text = ""

                    # Extract message text (support text, image, button replies, etc.)
                    if msg.get("type") == "text":
                        message_text = msg.get("text", {}).get("body", "")
                    elif msg.get("type") == "button":
                        message_text = msg.get("button", {}).get("text", "")
                    else:
                        message_text = f"[{msg.get('type', 'message')}]"

                    # Store in DB
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO messages (platform, sender_id, sender_name, message_text, received_at, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "whatsapp",
                            sender_id,
                            sender_name,
                            message_text,
                            datetime.utcnow().isoformat(),
                            "pending",
                        ),
                    )
                    conn.commit()
                    conn.close()

                    print(f"✅ WhatsApp message from {sender_name}: {message_text}")

    return jsonify({"status": "ok"}), 200


def send_whatsapp_message(phone_number: str, message_text: str) -> bool:
    """Send a WhatsApp message via Meta API"""
    if not WHATSAPP_API_TOKEN or not WHATSAPP_PHONE_ID:
        print("❌ WhatsApp API not configured")
        return False

    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_API_TOKEN}",
        "Content-Type": "application/json",
    }

    # Meta expects digits only in most cases (country code + number). Normalize safely.
    phone_number = "".join(ch for ch in str(phone_number) if ch.isdigit())
    if not phone_number:
        return False

    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "text",
        "text": {"body": message_text},
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            print(f"✅ WhatsApp message sent to {phone_number}")
            return True
        else:
            print(f"❌ WhatsApp error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ WhatsApp exception: {str(e)}")
        return False


@app.route("/whatsapp/send", methods=["POST"])
def whatsapp_send():
    """Admin endpoint to send WhatsApp message (requires ADMIN_TOKEN)"""
    if ADMIN_TOKEN and request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    phone = data.get("phone", "")
    message = data.get("message", "")

    if not phone or not message:
        return jsonify({"error": "Missing phone or message"}), 400

    success = send_whatsapp_message(phone, message)
    return jsonify({"success": success}), 200 if success else 500


@app.route("/messenger/send", methods=["POST"])
def messenger_send():
    """Admin endpoint to send a Messenger message (requires ADMIN_TOKEN)"""
    if ADMIN_TOKEN and request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    recipient_id = data.get("recipient_id") or data.get("user_id") or ""
    message = data.get("message", "")
    if not recipient_id or not message:
        return jsonify({"error": "Missing recipient_id or message"}), 400

    ok = send_message(recipient_id, message)
    return jsonify({"success": bool(ok)}), 200 if ok else 500


# ========================================
# Facebook Comments Improvements
# ========================================
@app.route("/facebook/comments", methods=["GET"])
def facebook_comments_verify():
    """Verify Facebook Webhook"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/facebook/comments", methods=["POST"])
def facebook_comments_webhook():
    """Receive and store Facebook comments"""
    data = request.json

    if not data.get("entry"):
        return jsonify({"status": "ok"}), 200

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            field = change.get("field")
            if field in ["feed", "comments", "mention"]:
                value = change.get("value", {})

                if value.get("verb") != "add":
                    continue

                if value.get("item") == "comment":
                    comment_id = value.get("comment_id")
                    post_id = value.get("post_id")
                    message = value.get("message", "")
                    sender_id = value.get("from", {}).get("id")
                    sender_name = value.get("from", {}).get("name", "Unknown")

                    # Store in DB
                    conn = get_db()
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT INTO comments (comment_id, post_id, sender_id, sender_name, comment_text, received_at, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            comment_id,
                            post_id,
                            sender_id,
                            sender_name,
                            message,
                            datetime.utcnow().isoformat(),
                            "pending",
                        ),
                    )
                    conn.commit()
                    conn.close()

                    print(f"✅ Facebook comment from {sender_name}: {message}")

    return jsonify({"status": "ok"}), 200


def reply_to_facebook_comment(comment_id: str, reply_text: str) -> bool:
    """Reply to a Facebook comment"""
    if not PAGE_ACCESS_TOKEN:
        return False

    url = f"https://graph.facebook.com/v18.0/{comment_id}/comments"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"message": reply_text}

    try:
        response = requests.post(url, params=params, json=data, timeout=10)
        if response.status_code == 200:
            # تحديث DB
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "UPDATE comments SET reply_text = ?, replied_at = ?, status = ? WHERE comment_id = ?",
                (reply_text, datetime.utcnow().isoformat(), "replied", comment_id),
            )
            conn.commit()
            conn.close()
            return True
        return False
    except Exception as e:
        print(f"❌ Facebook reply error: {str(e)}")
        return False


@app.route("/facebook/comments/reply", methods=["POST"])
def facebook_comment_reply():
    """Admin endpoint to reply to a Facebook comment"""
    if ADMIN_TOKEN and request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    comment_id = data.get("comment_id", "")
    reply = data.get("reply", "")

    if not comment_id or not reply:
        return jsonify({"error": "Missing comment_id or reply"}), 400

    success = reply_to_facebook_comment(comment_id, reply)
    return jsonify({"success": success}), 200 if success else 500


@app.route("/messages/list", methods=["GET"])
def get_messages_list():
    """Get all pending messages (WhatsApp + Facebook comments)"""
    if ADMIN_TOKEN and request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor()

    # الرسائل
    cur.execute(
        "SELECT id, platform, sender_id, sender_name, message_text, received_at, status FROM messages ORDER BY received_at DESC LIMIT 100"
    )
    messages = [
        {
            "id": row[0],
            "type": "message",
            "platform": row[1],
            "sender_id": row[2],
            "sender": row[3],
            "content": row[4],
            "received_at": row[5],
            "status": row[6],
            "reply_target": row[2],
        }
        for row in cur.fetchall()
    ]

    # التعليقات
    cur.execute(
        "SELECT id, comment_id, post_id, sender_id, sender_name, comment_text, received_at, status FROM comments ORDER BY received_at DESC LIMIT 100"
    )
    comments = [
        {
            "id": row[0],
            "type": "comment",
            "platform": "facebook",
            "comment_id": row[1],
            "post_id": row[2],
            "sender_id": row[3],
            "sender": row[4],
            "content": row[5],
            "received_at": row[6],
            "status": row[7],
            "reply_target": row[1],
        }
        for row in cur.fetchall()
    ]

    conn.close()

    # دمج الرسائل والتعليقات وترتيبها حسب الوقت
    all_items = sorted(
        messages + comments, key=lambda x: x.get("received_at", ""), reverse=True
    )

    return jsonify({"items": all_items}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
