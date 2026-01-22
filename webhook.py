from flask import Flask, request, jsonify, Response
import base64
import os
import random
import sqlite3
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from groq import Groq
import requests
import feedparser
from bs4 import BeautifulSoup
import pytz

from gsheets_cms import (
    SheetConfig,
    append_row,
    ensure_headers,
    find_due_scheduled,
    has_scheduled_within,
    list_rows,
    load_service_account_info_from_env,
    make_gspread_client,
    open_worksheet,
    update_fields,
    utc_now_iso,
)

app = Flask(__name__)

# API Keys from environment
GROQ_API_KEY = os.environ.get("GROQ_API_KEY_4")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "academy_webhook_2026")
# IMPORTANT: set CRON_SECRET in your hosting provider (Render env var). No insecure default.
CRON_SECRET = os.environ.get("CRON_SECRET", "").strip()
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")  # حماية احترافية لتوليد الأكواد (Header)

# Facebook reply toggles
FB_REPLY_COMMENTS = os.environ.get("FB_REPLY_COMMENTS", "1").strip().lower() in {
    "1",
    "true",
    "yes",
}
FB_REPLY_MESSAGES = os.environ.get("FB_REPLY_MESSAGES", "1").strip().lower() in {
    "1",
    "true",
    "yes",
}

# Google Sheets CMS
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_WORKSHEET = (
    os.environ.get("GOOGLE_SHEET_WORKSHEET", "Buffer").strip() or "Buffer"
)

# Telegram Webhook Uploader (single web server)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ADMIN_ID = int(os.environ.get("TELEGRAM_ADMIN_ID", "0") or "0")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY", "").strip()
TELEGRAM_PUBLISH_PASSPHRASE = os.environ.get(
    "TELEGRAM_PUBLISH_PASSPHRASE", "بسم الله الرحمن الرحيم"
).strip()

BUFFER_MINUTES = int(os.environ.get("BUFFER_MINUTES", "30") or "30")
PREFILL_HOURS = int(os.environ.get("PREFILL_HOURS", "6") or "6")

ACTIVE_HOURS_RAW = os.environ.get("ACTIVE_HOURS", "").strip()
if ACTIVE_HOURS_RAW:
    ACTIVE_HOURS = [int(x) for x in ACTIVE_HOURS_RAW.split(",") if x.strip().isdigit()]
else:
    ACTIVE_HOURS = []

_GS_CLIENT = None
_GS_WS = None
_GS_HEADER = None

_TELEGRAM_AUTH_UNTIL: Dict[int, datetime] = {}
_PENDING_VIDEO: Dict[int, Dict[str, str]] = {}

_CONTENT_TYPES = [
    "education_tip",  # تعليمي
    "marketing",  # تسويقي
    "motivation",  # تحفيزي
    "fun",  # خفيف/ترفيهي
    "self_defense",  # دفاع عن النفس
    "health_tip",  # صحة/تغذية
    "kids_advice",  # أولياء الأمور
    "training_drill",  # فني/تدريبي
]
_CONTENT_TYPE_INDEX = 0

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


@app.route("/self-test", methods=["GET"])
def self_test():
    """Safe smoke test (no posting).

    Protected via X-Admin-Token (if ADMIN_TOKEN is set).
    Checks env wiring + connectivity to Google Sheets / Telegram / Facebook.
    """
    auth = _require_admin()
    if auth:
        return jsonify(auth[0]), auth[1]

    results: Dict[str, Any] = {"ok": True, "checks": {}}

    def _add(name: str, ok: bool, detail: str = ""):
        results["checks"][name] = {"ok": ok, "detail": detail}
        if not ok:
            results["ok"] = False

    # --- Env presence (no secrets returned) ---
    _add("env.ADMIN_TOKEN", bool(ADMIN_TOKEN), "set" if ADMIN_TOKEN else "missing")
    _add("env.CRON_SECRET", bool(CRON_SECRET), "set" if CRON_SECRET else "missing")
    _add("env.VERIFY_TOKEN", bool(VERIFY_TOKEN), "set" if VERIFY_TOKEN else "missing")
    _add("env.GROQ_API_KEY_4", bool(GROQ_API_KEY), "set" if GROQ_API_KEY else "missing")
    _add(
        "env.PAGE_ACCESS_TOKEN",
        bool(PAGE_ACCESS_TOKEN),
        "set" if PAGE_ACCESS_TOKEN else "missing",
    )
    _add(
        "env.GOOGLE_SHEET_ID",
        bool(GOOGLE_SHEET_ID),
        "set" if GOOGLE_SHEET_ID else "missing",
    )
    _add(
        "env.GOOGLE_SERVICE_ACCOUNT",
        bool(
            os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
            or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
        ),
        (
            "set"
            if (
                os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
                or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
            )
            else "missing"
        ),
    )
    if os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE"):
        fp = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
        _add(
            "file.GOOGLE_SERVICE_ACCOUNT_FILE",
            os.path.exists(fp),
            "exists" if os.path.exists(fp) else "missing",
        )

    _add(
        "env.TELEGRAM_BOT_TOKEN",
        bool(TELEGRAM_BOT_TOKEN),
        "set" if TELEGRAM_BOT_TOKEN else "missing",
    )
    _add(
        "env.TELEGRAM_ADMIN_ID",
        bool(TELEGRAM_ADMIN_ID),
        "set" if TELEGRAM_ADMIN_ID else "missing",
    )
    _add(
        "env.TELEGRAM_WEBHOOK_SECRET",
        bool(TELEGRAM_WEBHOOK_SECRET),
        "set" if TELEGRAM_WEBHOOK_SECRET else "missing",
    )
    _add(
        "env.IMGBB_API_KEY", bool(IMGBB_API_KEY), "set" if IMGBB_API_KEY else "missing"
    )

    # --- Google Sheets connectivity (read/ensure headers only) ---
    try:
        if GOOGLE_SHEET_ID:
            ws, header = _get_sheet()
            _add("sheets.connect", True, f"worksheet={ws.title}")
            _add("sheets.headers", bool(header), f"columns={len(header)}")
        else:
            _add("sheets.connect", False, "GOOGLE_SHEET_ID missing")
    except Exception as e:
        msg = str(e).strip() or repr(e)
        _add("sheets.connect", False, f"{type(e).__name__}: {msg}")

    # --- Telegram connectivity (getMe) ---
    try:
        if TELEGRAM_BOT_TOKEN:
            r = requests.get(_telegram_api_url("getMe"), timeout=15)
            data = r.json() if r.content else {}
            _add(
                "telegram.getMe",
                bool(data.get("ok")),
                "ok" if data.get("ok") else str(data),
            )

            r2 = requests.get(_telegram_api_url("getWebhookInfo"), timeout=15)
            info = r2.json() if r2.content else {}
            url = ((info.get("result") or {}) if isinstance(info, dict) else {}).get(
                "url"
            )
            if info.get("ok") and url:
                _add("telegram.webhookInfo", True, str(url))
            else:
                _add("telegram.webhookInfo", False, str(info))
        else:
            _add("telegram.getMe", False, "TELEGRAM_BOT_TOKEN missing")
    except Exception as e:
        _add("telegram.getMe", False, str(e))

    # --- Facebook connectivity (read-only) ---
    try:
        if PAGE_ACCESS_TOKEN:
            r = requests.get(
                "https://graph.facebook.com/v18.0/me",
                params={"fields": "id,name", "access_token": PAGE_ACCESS_TOKEN},
                timeout=15,
            )
            data = r.json() if r.content else {}
            _add("facebook.me", "id" in data, "ok" if "id" in data else str(data))
        else:
            _add("facebook.me", False, "PAGE_ACCESS_TOKEN missing")
    except Exception as e:
        _add("facebook.me", False, str(e))

    return jsonify(results), (200 if results["ok"] else 207)


def _require_admin() -> Optional[Tuple[Dict[str, Any], int]]:
    if ADMIN_TOKEN and request.headers.get("X-Admin-Token") != ADMIN_TOKEN:
        return {"error": "Unauthorized"}, 401
    return None


def _get_sheet():
    global _GS_CLIENT, _GS_WS, _GS_HEADER

    if not GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID not configured")

    if _GS_WS is not None and _GS_HEADER is not None:
        return _GS_WS, _GS_HEADER

    svc = load_service_account_info_from_env()
    if not svc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON/FILE not configured")

    if _GS_CLIENT is None:
        _GS_CLIENT = make_gspread_client(svc)

    cfg = SheetConfig(sheet_id=GOOGLE_SHEET_ID, worksheet=GOOGLE_SHEET_WORKSHEET)
    ws = open_worksheet(_GS_CLIENT, cfg)
    header = ensure_headers(ws)
    _GS_WS, _GS_HEADER = ws, header
    return ws, header


def _pollinations_url(prompt_en: str) -> str:
    encoded = urllib.parse.quote(str(prompt_en or "").strip(), safe="")
    params = urllib.parse.urlencode(
        {
            "model": "anime",
            "width": 1024,
            "height": 1024,
            "nologo": "true",
            "seed": random.randint(1, 10_000_000),
        }
    )
    return f"https://image.pollinations.ai/prompt/{encoded}?{params}"


def _generate_image_prompt_en() -> str:
    if not client:
        return (
            "Anime-style illustration of kids martial arts training in Cairo gym,"
            " vibrant colors, clean lines, soft shading, no text, no watermark"
        )
    prompt = (
        "Write ONE short English image prompt (12-20 words) for an anime/cartoon sports academy scene in Egypt. "
        "Mention one sport (karate, kung fu, kickboxing, gymnastics, boxing, taekwondo). "
        "Add style details (vibrant colors, clean lines, soft shading). "
        "No text, no watermark, safe-for-work."
    )
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=80,
        temperature=0.9,
    )
    return (res.choices[0].message.content or "").strip().strip('"')


def _generate_image_prompt_from_text(ar_text: str) -> str:
    if not client:
        return (
            "Anime-style illustration of kids martial arts training in Cairo gym, "
            "vibrant colors, clean lines, soft shading, no text, no watermark"
        )
    prompt = (
        "Create ONE short English image prompt (12-20 words) that visually matches this Arabic post. "
        "Anime/cartoon style, vibrant colors, clean lines, soft shading. "
        "Mention one sport (karate, kung fu, kickboxing, gymnastics, boxing, taekwondo). "
        "No text, no watermark."
        f"\nPost (Arabic): {ar_text}"
    )
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=80,
        temperature=0.8,
    )
    return (res.choices[0].message.content or "").strip().strip('"')


def _generate_ar_caption_from_prompt(prompt_en: str) -> str:
    if not client:
        return "🥋 تدريب النهارده نار! جاهزين تبدأوا؟ احجز مكانك دلوقتي 💪📞"
    prompt = (
        "اكتب كابشن فيسبوك باللهجة المصرية الشيك (عامية مهذبة) لصانع محتوى رياضي محترف. "
        "الكابشن 3-5 سطور، معلومات مفيدة وقابلة للتطبيق، نصيحة تدريب أو صحة، "
        "تحفيز للّاعبين وأولياء الأمور، و CTA لطيف للحجز. "
        "اذكر واحدة من رياضات الأكاديمية (كاراتيه/كونغ فو/كيك بوكس/جمباز/ملاكمة/تايكوندو). "
        "إيموجيز بسيطة بدون مبالغة. "
        "ممنوع ذكر أو ترجمة وصف الصورة الإنجليزية أو كلمة prompt. "
        f"وصف الصورة (بالإنجليزية): {prompt_en}"
    )
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
        temperature=0.85,
    )
    return _clean_caption_text(res.choices[0].message.content or "")


def _next_available_slot(now_utc: datetime) -> datetime:
    candidate = now_utc + timedelta(minutes=max(BUFFER_MINUTES, 0))
    if not ACTIVE_HOURS:
        return candidate

    for _ in range(0, 72):
        if candidate.hour in ACTIVE_HOURS:
            return candidate
        candidate = (candidate + timedelta(hours=1)).replace(minute=0, second=0)
    return now_utc + timedelta(minutes=max(BUFFER_MINUTES, 0))


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


def _telegram_is_authorized(chat_id: int) -> bool:
    now = datetime.now(timezone.utc)
    expires = _TELEGRAM_AUTH_UNTIL.get(chat_id)
    return bool(expires and expires > now)


def _telegram_authorize(chat_id: int, minutes: int = 120) -> None:
    _TELEGRAM_AUTH_UNTIL[chat_id] = datetime.now(timezone.utc) + timedelta(
        minutes=minutes
    )


def _telegram_send_message_with_markup(
    chat_id: int, text: str, reply_markup: dict
) -> None:
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(
            _telegram_api_url("sendMessage"),
            json={"chat_id": chat_id, "text": text, "reply_markup": reply_markup},
            timeout=15,
        )
    except Exception:
        pass


def _telegram_video_category_markup() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "كاراتيه", "callback_data": "vid_cat:karate"},
                {"text": "كونغ فو", "callback_data": "vid_cat:kungfu"},
                {"text": "كيك بوكس", "callback_data": "vid_cat:kickboxing"},
            ],
            [
                {"text": "جمباز", "callback_data": "vid_cat:gymnastics"},
                {"text": "ملاكمة", "callback_data": "vid_cat:boxing"},
                {"text": "تايكوندو", "callback_data": "vid_cat:taekwondo"},
            ],
            [
                {"text": "عام", "callback_data": "vid_cat:general"},
            ],
        ]
    }


def _telegram_send_photo(chat_id: int, image_url: str, caption: str = "") -> None:
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(
            _telegram_api_url("sendPhoto"),
            data={"chat_id": chat_id, "photo": image_url, "caption": caption},
            timeout=30,
        )
    except Exception:
        pass


def _telegram_admin_help() -> str:
    return (
        "لوحة تيليجرام (أوامر الأدمن):\n"
        "/menu - فتح لوحة التحكم\n"
        "/auth <pass> - تفعيل النشر لمدة ساعتين\n"
        "/queue - عرض آخر 10 منشورات مجدولة\n"
        "/post <row> - نشر فوري لصف محدد\n"
        "/delete <row> - حذف صف\n"
        "/caption <row> <text> - تعديل الكابشن\n"
        "/status - حالة الطابور\n"
    )


def _telegram_admin_menu_markup() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "📊 الحالة", "callback_data": "dash_status"},
                {"text": "🗂️ الطابور", "callback_data": "dash_queue"},
            ],
            [
                {"text": "🤖 AI انشر الآن", "callback_data": "dash_ai_post"},
                {"text": "⚡ نشر فوري", "callback_data": "dash_post"},
                {"text": "📝 تعديل كابشن", "callback_data": "dash_caption"},
            ],
            [
                {"text": "🗑️ حذف صف", "callback_data": "dash_delete"},
                {"text": "❓ مساعدة", "callback_data": "dash_help"},
            ],
        ]
    }


def _telegram_admin_menu(chat_id: int) -> None:
    _telegram_send_message_with_markup(
        chat_id,
        "لوحة تحكم الأكاديمية ✅\nاختر من القائمة:",
        _telegram_admin_menu_markup(),
    )


def _telegram_handle_admin_callback(chat_id: int, data: str) -> None:
    if data == "dash_help":
        _telegram_send_message(chat_id, _telegram_admin_help())
        return
    if data == "dash_status":
        ws, _header = _get_sheet()
        rows = list_rows(ws)
        pending = [
            r for r in rows if str(r.get("Status", "")).strip().lower() == "scheduled"
        ]
        _telegram_send_message(chat_id, f"📊 Scheduled: {len(pending)}")
        return

    if data == "dash_queue":
        ws, _header = _get_sheet()
        rows = list_rows(ws)
        pending = [
            r for r in rows if str(r.get("Status", "")).strip().lower() == "scheduled"
        ]
        pending.sort(key=lambda r: str(r.get("Scheduled_Time") or ""))
        if not pending:
            _telegram_send_message(chat_id, "لا توجد منشورات مجدولة حالياً.")
            return
        lines = []
        for r in pending[:10]:
            row_no = int(r.get("_row_number") or 0)
            sched = str(r.get("Scheduled_Time") or "").strip()
            cap = str(r.get("AI_Caption") or "").strip().replace("\n", " ")
            if len(cap) > 60:
                cap = cap[:57] + "..."
            lines.append(f"#{row_no} • {sched}\n{cap}")
        _telegram_send_message(chat_id, "\n\n".join(lines))
        return

    if data == "dash_post":
        _telegram_send_message(chat_id, "اكتب: /post <row>")
        return

    if data == "dash_caption":
        _telegram_send_message(chat_id, "اكتب: /caption <row> <text>")
        return

    if data == "dash_delete":
        _telegram_send_message(chat_id, "اكتب: /delete <row>")
        return

    if data == "dash_ai_post":
        prompt_en = _generate_image_prompt_en()
        caption_ar = _generate_ar_caption_from_prompt(prompt_en)
        prompt_en = _generate_image_prompt_from_text(caption_ar)
        img_url = _pollinations_url(prompt_en)
        ok, err = _post_to_facebook_page(caption_ar, img_url)

        try:
            ws, header = _get_sheet()
            append_row(
                ws,
                header,
                {
                    "Timestamp": utc_now_iso(),
                    "Image_URL": img_url,
                    "AI_Caption": caption_ar,
                    "Status": "Posted" if ok else "Failed",
                    "Scheduled_Time": "",
                    "Source": "AI_Generated",
                },
            )
        except Exception:
            pass

        if ok:
            _telegram_send_message(chat_id, "✅ تم نشر محتوى وصورة AI الآن")
        else:
            _telegram_send_message(chat_id, f"❌ فشل النشر: {err}")
        return

    if data.startswith("vid_cat:"):
        info = _PENDING_VIDEO.get(chat_id)
        if not info:
            _telegram_send_message(chat_id, "❌ مفيش فيديو مُعلّق.")
            return
        topic = data.split(":", 1)[1]
        try:
            video_bytes = _telegram_download_file(info["file_id"])
            caption = _generate_caption_for_video_with_context(topic)
            ok, err = _post_video_to_facebook_page(
                caption,
                video_bytes,
                info.get("filename", "video.mp4"),
                info.get("mime_type", "video/mp4"),
            )

            try:
                ws, header = _get_sheet()
                append_row(
                    ws,
                    header,
                    {
                        "Timestamp": utc_now_iso(),
                        "Image_URL": "",
                        "AI_Caption": caption,
                        "Status": "Posted" if ok else "Failed",
                        "Scheduled_Time": "",
                        "Source": "User_Video",
                    },
                )
            except Exception:
                pass

            if ok:
                _telegram_send_message(chat_id, "✅ تم نشر الفيديو مع كابشن.")
            else:
                _telegram_send_message(chat_id, f"❌ فشل نشر الفيديو: {err}")
        finally:
            _PENDING_VIDEO.pop(chat_id, None)
        return


def _telegram_handle_admin_command(chat_id: int, text: str) -> None:
    cmd = (text or "").strip()
    if not cmd:
        return

    if cmd.startswith("/help"):
        _telegram_send_message(chat_id, _telegram_admin_help())
        return

    if cmd.startswith("/start") or cmd.startswith("/menu"):
        _telegram_admin_menu(chat_id)
        return

    if cmd.startswith("/auth "):
        phrase = cmd.split(" ", 1)[1].strip()
        if phrase == TELEGRAM_PUBLISH_PASSPHRASE:
            _telegram_authorize(chat_id)
            _telegram_send_message(chat_id, "✅ تم التفعيل لمدة ساعتين.")
        else:
            _telegram_send_message(chat_id, "❌ كلمة السر غير صحيحة.")
        return

    if cmd.startswith("/status"):
        ws, _header = _get_sheet()
        rows = list_rows(ws)
        pending = [
            r for r in rows if str(r.get("Status", "")).strip().lower() == "scheduled"
        ]
        _telegram_send_message(chat_id, f"Scheduled: {len(pending)}")
        return

    if cmd.startswith("/queue"):
        ws, _header = _get_sheet()
        rows = list_rows(ws)
        pending = [
            r for r in rows if str(r.get("Status", "")).strip().lower() == "scheduled"
        ]
        pending.sort(key=lambda r: str(r.get("Scheduled_Time") or ""))
        if not pending:
            _telegram_send_message(chat_id, "لا توجد منشورات مجدولة حالياً.")
            return
        lines = []
        for r in pending[:10]:
            row_no = int(r.get("_row_number") or 0)
            sched = str(r.get("Scheduled_Time") or "").strip()
            cap = str(r.get("AI_Caption") or "").strip().replace("\n", " ")
            if len(cap) > 60:
                cap = cap[:57] + "..."
            lines.append(f"#{row_no} • {sched}\n{cap}")
        _telegram_send_message(chat_id, "\n\n".join(lines))
        return

    if cmd.startswith("/post "):
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            _telegram_send_message(chat_id, "استخدم: /post <row>")
            return
        row_number = int(parts[1].strip())
        ws, header = _get_sheet()
        values = ws.row_values(row_number)
        item = {
            header[i]: (values[i] if i < len(values) else "")
            for i in range(len(header))
        }
        caption = str(item.get("AI_Caption") or "").strip()
        image_url = str(item.get("Image_URL") or "").strip() or None
        ok, err = _post_to_facebook_page(caption, image_url)
        if ok:
            update_fields(ws, row_number, header, {"Status": "Posted"})
            _telegram_send_message(chat_id, f"✅ Posted row {row_number}")
        else:
            update_fields(ws, row_number, header, {"Status": "Failed"})
            _telegram_send_message(chat_id, f"❌ Failed: {err}")
        return

    if cmd.startswith("/delete "):
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            _telegram_send_message(chat_id, "استخدم: /delete <row>")
            return
        row_number = int(parts[1].strip())
        ws, _header = _get_sheet()
        ws.delete_rows(row_number)
        _telegram_send_message(chat_id, f"🗑️ Deleted row {row_number}")
        return

    if cmd.startswith("/caption "):
        parts = cmd.split(maxsplit=2)
        if len(parts) < 3 or not parts[1].strip().isdigit():
            _telegram_send_message(chat_id, "استخدم: /caption <row> <text>")
            return
        row_number = int(parts[1].strip())
        new_caption = parts[2].strip()
        ws, header = _get_sheet()
        update_fields(ws, row_number, header, {"AI_Caption": new_caption})
        _telegram_send_message(chat_id, f"✅ Updated caption for row {row_number}")
        return

    _telegram_send_message(chat_id, "أمر غير معروف. اكتب /help")


def _telegram_download_file(file_id: str) -> bytes:
    r = requests.get(
        _telegram_api_url("getFile"), params={"file_id": file_id}, timeout=20
    )
    payload = r.json() if r.content else {}
    if not payload.get("ok"):
        raise RuntimeError("Telegram getFile failed")
    file_path = (payload.get("result") or {}).get("file_path")
    if not file_path:
        raise RuntimeError("Telegram file_path missing")
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    img = requests.get(file_url, timeout=60)
    img.raise_for_status()
    return img.content


def _imgbb_upload(image_bytes: bytes) -> str:
    if not IMGBB_API_KEY:
        raise RuntimeError("IMGBB_API_KEY not set")
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": IMGBB_API_KEY, "image": b64},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json() if resp.content else {}
    if not data.get("success"):
        raise RuntimeError("ImgBB upload failed")
    return str((data.get("data") or {}).get("url") or "").strip()


def _generate_caption_for_image_url(image_url: str) -> str:
    if not client:
        return "🥋 جاهزين للتمرين؟ احجز مكانك دلوقتي! 📞"
    prompt = (
        "اكتب كابشن فيسبوك باللهجة المصرية الشيك (عامية مهذبة) لصانع محتوى رياضي محترف. "
        "الكابشن 3-5 سطور، معلومات مفيدة قابلة للتطبيق، نصيحة تدريب أو صحة، "
        "تحفيز للّاعبين وأولياء الأمور، و CTA لطيف للحجز. "
        "اذكر واحدة من رياضات الأكاديمية (كاراتيه/كونغ فو/كيك بوكس/جمباز/ملاكمة/تايكوندو). "
        "إيموجيز بسيطة بدون مبالغة. "
        "لا تذكر أنك لم ترَ الصورة. "
        "ممنوع ذكر أو ترجمة وصف الصورة الإنجليزية أو كلمة prompt. "
        f"رابط الصورة (للسياق فقط): {image_url}"
    )
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
        temperature=0.85,
    )
    return _clean_caption_text(res.choices[0].message.content or "")


def _clean_caption_text(text: str) -> str:
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    banned = ("prompt", "english", "description", "وصف الصورة", "image prompt")
    filtered = [ln for ln in lines if all(b not in ln.lower() for b in banned)]
    return "\n".join(filtered).strip() or str(text or "").strip()


def _generate_caption_for_video() -> str:
    if not client:
        return "🎥 تمرين قوي ومفيد! احجز مكانك دلوقتي 💪📞"
    prompt = (
        "اكتب كابشن فيسبوك باللهجة المصرية الشيك (عامية مهذبة) لفيديو تدريب رياضي في الأكاديمية. "
        "الكابشن 3-5 سطور، نصيحة تدريب أو صحة، تحفيز للّاعبين وأولياء الأمور، "
        "و CTA لطيف للحجز. اذكر رياضة من رياضات الأكاديمية."
    )
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
        temperature=0.85,
    )
    return (res.choices[0].message.content or "").strip()


def _generate_caption_for_video_with_context(topic: str) -> str:
    if not client:
        return "🎥 تمرين ممتع ومفيد! احجز مكانك دلوقتي 💪📞"
    topic_map = {
        "karate": "كاراتيه",
        "kungfu": "كونغ فو",
        "kickboxing": "كيك بوكسينج",
        "gymnastics": "جمباز",
        "boxing": "ملاكمة",
        "taekwondo": "تايكوندو",
        "general": "رياضة",
    }
    sport = topic_map.get(topic, "رياضة")
    prompt = (
        "اكتب كابشن فيسبوك باللهجة المصرية الشيك (عامية مهذبة) لفيديو تدريب رياضي في الأكاديمية. "
        "الكابشن 3-5 سطور، نصيحة عملية، تحفيز للّاعبين وأولياء الأمور، و CTA لطيف للحجز. "
        f"اذكر رياضة: {sport}."
    )
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
        temperature=0.85,
    )
    return (res.choices[0].message.content or "").strip()


def _generate_caption_for_video_from_text(text: str) -> str:
    if not client:
        return "🎥 تمرين ممتع ومفيد! احجز مكانك دلوقتي 💪📞"
    prompt = (
        "اكتب كابشن فيسبوك باللهجة المصرية الشيك (عامية مهذبة) لفيديو تدريب رياضي في الأكاديمية. "
        "الكابشن 3-5 سطور، نصيحة عملية، تحفيز للّاعبين وأولياء الأمور، و CTA لطيف للحجز. "
        f"وصف الفيديو: {text}"
    )
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
        temperature=0.85,
    )
    return (res.choices[0].message.content or "").strip()


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
        "كاراتيه": "600 جنيه/شهر",
        "كونغ فو": "600 جنيه/شهر",
        "كيك بوكسينج": "600 جنيه/شهر",
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


SYSTEM_PROMPT_BASE = """أنت "كابتن عز غريب"، صانع محتوى رياضي ودفاع عن النفس محترف.
هدفك: تقديم قيمة حقيقية، معلومات عملية قابلة للتطبيق، وتحفيز اللاعبين وأولياء الأمور.

إرشادات أسلوبية:
- قدّم نصائح واقعية ومختصرة عن اللياقة، المرونة، القوة، التغذية البسيطة، السلامة.
- ركّز على رياضات الأكاديمية: كاراتيه، كونغ فو، كيك بوكسينج، جمباز، ملاكمة، تايكوندو.
- ممنوع ذكر كرة القدم أو أي رياضة غير رياضات الأكاديمية.
- أضف نقاط تعليمية عن الدفاع عن النفس والانضباط والثقة.
- اختم بنداء لطيف للحجز أو التواصل (CTA) دون مبالغة.
- خاطب الجميع بلغة عربية مصرية سهلة ومهذبة.
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
        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            return twitter_image["content"]

        return None
    except:
        return None


def fetch_content_idea():
    """Fetch an idea from RSS or generate a topic based on time of day"""
    # توزيع متساوٍ (Round-robin)
    global _CONTENT_TYPE_INDEX
    post_type = _CONTENT_TYPES[_CONTENT_TYPE_INDEX % len(_CONTENT_TYPES)]
    _CONTENT_TYPE_INDEX += 1

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
    if not client:
        return None

    if idea["type"] == "curated":
        prompt = f"""
        أنت كابتن عز غريب.
        {get_mood_prompt(BOT_CONFIG['system_prompt_mood'])}
        
        لقيت المقال ده عن الرياضة:
        العنوان: {idea['title']}
        الملخص: {idea['summary']}
        
        اكتب بوست فيسبوك تعلق فيه على الموضوع ده.
        1. ابدأ بجملة تشد الانتباه (Hook).
        2. لخص الفكرة المهمة باختصار باللهجة المصرية الشيك.
        3. ضيف نصيحة إضافية من عندك "تكة الكابتن".
        4. (اختياري) لو مناسب، اربط الموضوع برياضة موجودة في الأكاديمية عندنا.
        5. لا تذكر الرابط، فقط علق على المحتوى.
        """
    else:
        topics = {
            "education_tip": "معلومة تعليمية مبسطة عن رياضة من رياضات الأكاديمية وفايدتها.",
            "marketing": "بوست تسويقي محترف يوضح قيمة التدريب ويدعو للحجز.",
            "motivation": "بوست تحفيزي للاعبين وأولياء الأمور عن الانضباط والاستمرارية.",
            "fun": "بوست خفيف ولطيف مرتبط بالتمرين والالتزام بدون مبالغة.",
            "self_defense": "نصيحة دفاع عن النفس آمنة ومناسبة للأعمار المختلفة.",
            "health_tip": "نصيحة تغذية أو شرب مياه أو نوم للرياضيين.",
            "kids_advice": "نصيحة لأولياء الأمور عن التعامل مع طاقة الأطفال وتوجيهها للرياضة.",
            "training_drill": "معلومة فنية بسيطة عن الكاراتيه أو الجمباز أو الكونفو.",
        }
        topic_desc = topics.get(idea["category"], "نصيحة رياضية عامة")

        prompt = f"""
        أنت كابتن عز غريب.
        {get_mood_prompt(BOT_CONFIG['system_prompt_mood'])}

        اكتب بوست فيسبوك عن: {topic_desc}
        
        الأسلوب:
        - لهجة مصرية شيك (عامية مهذبة).
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


def _post_to_facebook_page(message: str, image_url: Optional[str]) -> Tuple[bool, str]:
    if not PAGE_ACCESS_TOKEN:
        return False, "PAGE_ACCESS_TOKEN not set"

    params = {"access_token": PAGE_ACCESS_TOKEN}

    if image_url:
        try:
            img_resp = requests.get(image_url, timeout=30)
            img_resp.raise_for_status()
            content_type = img_resp.headers.get("content-type", "image/jpeg")
            files = {"source": ("image", img_resp.content, content_type)}
            data = {"caption": message}
            r = requests.post(
                "https://graph.facebook.com/v18.0/me/photos",
                params=params,
                data=data,
                files=files,
                timeout=45,
            )
            if r.status_code == 200:
                return True, "ok"
        except Exception:
            pass

        try:
            url = "https://graph.facebook.com/v18.0/me/photos"
            data = {"url": image_url, "caption": message}
            r = requests.post(url, params=params, json=data, timeout=30)
            if r.status_code == 200:
                return True, "ok"
        except Exception:
            pass

    try:
        url = "https://graph.facebook.com/v18.0/me/feed"
        data = {"message": message}
        if image_url and "pollinations.ai/prompt" not in image_url:
            data["link"] = image_url
        r = requests.post(url, params=params, json=data, timeout=30)
        r.raise_for_status()
        return True, "ok"
    except Exception as e:
        return False, str(e)


def _post_video_to_facebook_page(
    message: str, video_bytes: bytes, filename: str, mime_type: str
) -> Tuple[bool, str]:
    if not PAGE_ACCESS_TOKEN:
        return False, "PAGE_ACCESS_TOKEN not set"

    params = {"access_token": PAGE_ACCESS_TOKEN}
    try:
        files = {"source": (filename, video_bytes, mime_type)}
        data = {"description": message}
        r = requests.post(
            "https://graph.facebook.com/v18.0/me/videos",
            params=params,
            data=data,
            files=files,
            timeout=120,
        )
        if r.status_code == 200:
            return True, "ok"
        return False, r.text
    except Exception as e:
        return False, str(e)


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
    if not CRON_SECRET:
        return "CRON_SECRET is not configured", 500
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
    if not CRON_SECRET:
        return "CRON_SECRET is not configured", 500
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


@app.route("/publisher-tick", methods=["GET"])
def publisher_tick():
    """Minute-level publisher tick.

    - Publishes due scheduled items from Google Sheets.
    - If queue is empty and no scheduled items in next PREFILL_HOURS, pre-fills one AI-generated item.
    """
    if not CRON_SECRET:
        return "CRON_SECRET is not configured", 500
    secret = request.args.get("secret")
    if secret != CRON_SECRET:
        return "Unauthorized", 401

    dry_run = str(request.args.get("dry_run", "")).strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if not GOOGLE_SHEET_ID:
        return (
            jsonify({"enabled": False, "error": "GOOGLE_SHEET_ID not configured"}),
            200,
        )

    try:
        ws, header = _get_sheet()
        rows = list_rows(ws)

        # 1) Publish due
        due = find_due_scheduled(rows)
        if due:
            item = due[0]
            row_number = int(item.get("_row_number") or 0)
            caption = str(item.get("AI_Caption") or "").strip()
            image_url = str(item.get("Image_URL") or "").strip() or None

            if dry_run:
                update_fields(ws, row_number, header, {"Status": "Posted"})
                return (
                    jsonify(
                        {"enabled": True, "action": "dry_run_posted", "row": row_number}
                    ),
                    200,
                )

            ok, err = _post_to_facebook_page(caption, image_url)
            if ok:
                update_fields(ws, row_number, header, {"Status": "Posted"})
                return (
                    jsonify({"enabled": True, "action": "posted", "row": row_number}),
                    200,
                )
            update_fields(ws, row_number, header, {"Status": "Failed"})
            return (
                jsonify(
                    {
                        "enabled": True,
                        "action": "failed",
                        "row": row_number,
                        "error": err,
                    }
                ),
                200,
            )

        # 2) Prefill if needed
        if PREFILL_HOURS > 0:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            window_end = now + timedelta(hours=max(PREFILL_HOURS, 1))
            if not has_scheduled_within(rows, start=now, end=window_end):
                prompt_en = _generate_image_prompt_en()
                caption_ar = _generate_ar_caption_from_prompt(prompt_en)
                prompt_en = _generate_image_prompt_from_text(caption_ar)
                img_url = _pollinations_url(prompt_en)
                scheduled_time = _next_available_slot(now)
                append_row(
                    ws,
                    header,
                    {
                        "Timestamp": utc_now_iso(),
                        "Image_URL": img_url,
                        "AI_Caption": caption_ar,
                        "Status": "Scheduled",
                        "Scheduled_Time": scheduled_time.isoformat(),
                        "Source": "AI_Generated",
                    },
                )
                return jsonify({"enabled": True, "action": "prefilled"}), 200

        return jsonify({"enabled": True, "action": "noop"}), 200
    except Exception as e:
        return jsonify({"enabled": True, "action": "error", "error": str(e)}), 500


@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    """Telegram webhook uploader (admin-only)."""
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if TELEGRAM_WEBHOOK_SECRET and secret != TELEGRAM_WEBHOOK_SECRET:
        return jsonify({"ok": False, "error": "unauthorized"}), 403

    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"ok": False, "error": "TELEGRAM_BOT_TOKEN not configured"}), 500

    if not GOOGLE_SHEET_ID:
        return jsonify({"ok": False, "error": "GOOGLE_SHEET_ID not configured"}), 500

    update = request.get_json(silent=True) or {}

    # Inline button callbacks
    callback = update.get("callback_query") or {}
    if callback:
        cb_from = callback.get("from") or {}
        cb_id = cb_from.get("id")
        cb_message = callback.get("message") or {}
        cb_chat = cb_message.get("chat") or {}
        cb_chat_id = cb_chat.get("id")
        data = str(callback.get("data") or "")

        if TELEGRAM_ADMIN_ID and cb_id != TELEGRAM_ADMIN_ID:
            return jsonify({"ok": True})

        if cb_chat_id:
            try:
                _telegram_handle_admin_callback(int(cb_chat_id), data)
            except Exception as e:
                _telegram_send_message(int(cb_chat_id), f"❌ Error: {str(e)}")
        return jsonify({"ok": True})

    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    from_user = message.get("from") or {}
    from_id = from_user.get("id")

    text = str(message.get("text") or "").strip()

    # Passphrase gate for uploads/content (available to any user)
    if (
        text
        and TELEGRAM_PUBLISH_PASSPHRASE
        and text.strip() == TELEGRAM_PUBLISH_PASSPHRASE
    ):
        _telegram_authorize(int(chat_id))
        _telegram_send_message(
            int(chat_id), "✅ تم التفعيل لمدة ساعتين. ابعت المحتوى الآن."
        )
        return jsonify({"ok": True})

    # Admin-only commands/menu
    if text and text.startswith("/"):
        if TELEGRAM_ADMIN_ID and from_id != TELEGRAM_ADMIN_ID:
            if chat_id:
                _telegram_send_message(
                    int(chat_id),
                    "الأوامر للأدمن فقط. لو هتنشر محتوى اكتب كلمة السر أولاً.",
                )
            return jsonify({"ok": True})

        try:
            _telegram_handle_admin_command(int(chat_id), text)
        except Exception as e:
            _telegram_send_message(int(chat_id), f"❌ Error: {str(e)}")
        return jsonify({"ok": True})

    if not _telegram_is_authorized(int(chat_id)):
        if chat_id:
            _telegram_send_message(
                int(chat_id), "🔒 اكتب كلمة السر لتفعيل النشر لمدة ساعتين."
            )
        return jsonify({"ok": True})

    # Handle video uploads
    video = message.get("video")
    doc = message.get("document") or {}
    doc_mime = str(doc.get("mime_type") or "")
    if video or doc_mime.startswith("video/"):
        file_id = None
        filename = "video.mp4"
        mime_type = "video/mp4"
        caption_text = str(message.get("caption") or "").strip()

        if video:
            file_id = video.get("file_id")
            filename = str(video.get("file_name") or "video.mp4")
            mime_type = str(video.get("mime_type") or "video/mp4")
        else:
            file_id = doc.get("file_id")
            filename = str(doc.get("file_name") or "video.mp4")
            mime_type = str(doc.get("mime_type") or "video/mp4")

        if not file_id:
            _telegram_send_message(int(chat_id), "❌ لم أستطع قراءة الفيديو.")
            return jsonify({"ok": True})

        # If caption provided, generate caption from it and post immediately
        if caption_text:
            try:
                video_bytes = _telegram_download_file(str(file_id))
                caption = _generate_caption_for_video_from_text(caption_text)
                ok, err = _post_video_to_facebook_page(
                    caption, video_bytes, filename, mime_type
                )

                try:
                    ws, header = _get_sheet()
                    append_row(
                        ws,
                        header,
                        {
                            "Timestamp": utc_now_iso(),
                            "Image_URL": "",
                            "AI_Caption": caption,
                            "Status": "Posted" if ok else "Failed",
                            "Scheduled_Time": "",
                            "Source": "User_Video",
                        },
                    )
                except Exception:
                    pass

                if ok:
                    _telegram_send_message(int(chat_id), "✅ تم نشر الفيديو مع كابشن.")
                else:
                    _telegram_send_message(int(chat_id), f"❌ فشل نشر الفيديو: {err}")
                return jsonify({"ok": True})
            except Exception as e:
                _telegram_send_message(int(chat_id), f"❌ Error: {str(e)}")
                return jsonify({"ok": True})

        _PENDING_VIDEO[int(chat_id)] = {
            "file_id": str(file_id),
            "filename": filename,
            "mime_type": mime_type,
        }
        _telegram_send_message_with_markup(
            int(chat_id),
            "الفيديو عن إيه؟ اختار النوع علشان أكتب كابشن مناسب:",
            _telegram_video_category_markup(),
        )
        return jsonify({"ok": True})

    photos = message.get("photo") or []
    if not photos:
        if chat_id:
            # Allow text-only content scheduling
            if text and not text.startswith("/"):
                now = datetime.now(timezone.utc).replace(microsecond=0)
                scheduled_time = now + timedelta(minutes=max(BUFFER_MINUTES, 0))
                ws, header = _get_sheet()
                append_row(
                    ws,
                    header,
                    {
                        "Timestamp": utc_now_iso(),
                        "Image_URL": "",
                        "AI_Caption": text,
                        "Status": "Scheduled",
                        "Scheduled_Time": scheduled_time.isoformat(),
                        "Source": "User_Text",
                    },
                )
                _telegram_send_message(
                    int(chat_id),
                    f"✅ تم حفظ المحتوى. موعد النشر: {scheduled_time.isoformat()}",
                )
            else:
                _telegram_send_message(int(chat_id), "ابعت صورة أو محتوى نصي.")
        return jsonify({"ok": True})

    best = photos[-1]
    file_id = best.get("file_id")
    if not file_id:
        return jsonify({"ok": True})

    try:
        image_bytes = _telegram_download_file(str(file_id))
        image_url = _imgbb_upload(image_bytes)
        caption = _generate_caption_for_image_url(image_url)

        now = datetime.now(timezone.utc).replace(microsecond=0)
        scheduled_time = now + timedelta(minutes=max(BUFFER_MINUTES, 0))

        ws, header = _get_sheet()
        append_row(
            ws,
            header,
            {
                "Timestamp": utc_now_iso(),
                "Image_URL": image_url,
                "AI_Caption": caption,
                "Status": "Scheduled",
                "Scheduled_Time": scheduled_time.isoformat(),
                "Source": "User_Upload",
            },
        )

        if chat_id:
            _telegram_send_message(
                int(chat_id),
                f"✅ Saved to queue. Will post in {BUFFER_MINUTES} mins.\n⏰ {scheduled_time.isoformat()}",
            )
        return jsonify({"ok": True, "image_url": image_url}), 200
    except Exception as e:
        if chat_id:
            _telegram_send_message(int(chat_id), f"❌ Error: {str(e)}")
        return jsonify({"ok": True}), 200


@app.route("/cms/pending", methods=["GET"])
def cms_pending():
    auth = _require_admin()
    if auth:
        return jsonify(auth[0]), auth[1]

    ws, _header = _get_sheet()
    rows = list_rows(ws)
    pending = [
        r for r in rows if str(r.get("Status", "")).strip().lower() == "scheduled"
    ]
    pending.sort(key=lambda r: str(r.get("Scheduled_Time") or ""))
    return jsonify({"items": pending}), 200


@app.route("/cms/update-caption", methods=["POST"])
def cms_update_caption():
    auth = _require_admin()
    if auth:
        return jsonify(auth[0]), auth[1]

    payload = request.get_json(silent=True) or {}
    row_number = int(payload.get("row_number") or 0)
    caption = str(payload.get("caption") or "")
    if row_number < 2:
        return jsonify({"error": "row_number required"}), 400

    ws, header = _get_sheet()
    update_fields(ws, row_number, header, {"AI_Caption": caption})
    return jsonify({"ok": True}), 200


@app.route("/cms/post-now", methods=["POST"])
def cms_post_now():
    auth = _require_admin()
    if auth:
        return jsonify(auth[0]), auth[1]

    payload = request.get_json(silent=True) or {}
    row_number = int(payload.get("row_number") or 0)
    if row_number < 2:
        return jsonify({"error": "row_number required"}), 400

    ws, header = _get_sheet()
    # Read row
    values = ws.row_values(row_number)
    item = {
        header[i]: (values[i] if i < len(values) else "") for i in range(len(header))
    }
    caption = str(item.get("AI_Caption") or "").strip()
    image_url = str(item.get("Image_URL") or "").strip() or None
    ok, err = _post_to_facebook_page(caption, image_url)
    if ok:
        update_fields(ws, row_number, header, {"Status": "Posted"})
        return jsonify({"ok": True}), 200
    update_fields(ws, row_number, header, {"Status": "Failed"})
    return jsonify({"ok": False, "error": err}), 500


@app.route("/cms/delete", methods=["POST"])
def cms_delete():
    auth = _require_admin()
    if auth:
        return jsonify(auth[0]), auth[1]

    payload = request.get_json(silent=True) or {}
    row_number = int(payload.get("row_number") or 0)
    if row_number < 2:
        return jsonify({"error": "row_number required"}), 400

    ws, _header = _get_sheet()
    ws.delete_rows(row_number)
    return jsonify({"ok": True}), 200


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """Webhook verification for Facebook"""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ Webhook verified successfully!")
        return (challenge or ""), 200
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
            page_id = str(entry.get("id") or "")
            # Handle Messenger Messages
            for messaging in entry.get("messaging", []):
                sender_id = str(messaging.get("sender", {}).get("id") or "")

                if not FB_REPLY_MESSAGES:
                    continue

                if page_id and sender_id == page_id:
                    continue

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
                    if not FB_REPLY_COMMENTS:
                        continue
                    value = change.get("value", {})

                    # Only reply to NEW comments (add)
                    if value.get("verb") != "add":
                        continue

                    if value.get("item") == "comment":
                        comment_id = value.get("comment_id")
                        message = value.get("message", "")
                        sender_id = str(value.get("from", {}).get("id") or "")

                        if page_id and sender_id == page_id:
                            continue

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
