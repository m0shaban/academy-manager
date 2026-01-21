import base64
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO

import requests
from groq import Groq
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from gsheets_cms import (
    SheetConfig,
    append_scheduled_post,
    ensure_headers,
    load_service_account_info_from_env,
    make_gspread_client,
    open_worksheet,
)


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = int(os.environ.get("TELEGRAM_ADMIN_ID", "0") or "0")
IMGBB_API_KEY = os.environ.get("IMGBB_API_KEY", "")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY_4", "")

GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_WORKSHEET = os.environ.get("GOOGLE_SHEET_WORKSHEET", "Buffer")

BUFFER_MINUTES = int(os.environ.get("BUFFER_MINUTES", "30") or "30")


def _upload_to_imgbb(image_bytes: bytes) -> str:
    if not IMGBB_API_KEY:
        raise RuntimeError("IMGBB_API_KEY not set")

    payload = {
        "key": IMGBB_API_KEY,
        "image": base64.b64encode(image_bytes).decode("utf-8"),
        "name": f"telegram_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
    }

    resp = requests.post("https://api.imgbb.com/1/upload", data=payload, timeout=45)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError("ImgBB upload failed")
    return data["data"]["url"]


def _generate_ai_caption(image_url: str) -> str:
    # Note: text-only model. We generate a strong generic caption suitable for academy posts.
    if not GROQ_API_KEY:
        return "🥋 جاهزين للتمرين؟ تعالوا نكمل مشوار القوة والانضباط… احجز مكانك دلوقتي! 📞"

    client = Groq(api_key=GROQ_API_KEY)
    prompt = (
        "اكتب كابشن فيسبوك عربي مصري (عامية) عن صورة تدريب أطفال في أكاديمية فنون قتالية/جمباز. "
        "الكابشن يكون قصير ومقسّم سطرين إلى 4 أسطر، فيه تحفيز + CTA للحجز + إيموجيز مناسبة. "
        "لا تذكر أنك لم ترَ الصورة. "
        f"رابط الصورة (للسياق فقط): {image_url}"
    )

    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
        temperature=0.8,
    )
    return (res.choices[0].message.content or "").strip()


def _get_sheet_ws():
    if not GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID not set")

    svc = load_service_account_info_from_env()
    if not svc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not set")

    client = make_gspread_client(svc)
    cfg = SheetConfig(sheet_id=GOOGLE_SHEET_ID, worksheet=GOOGLE_SHEET_WORKSHEET)
    ws = open_worksheet(client, cfg)
    ensure_headers(ws)
    return ws


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.photo:
        return

    user_id = update.effective_user.id if update.effective_user else 0
    if TELEGRAM_ADMIN_ID and user_id != TELEGRAM_ADMIN_ID:
        return

    await update.message.reply_text("📥 استلمت الصورة… جاري الرفع وتجهيز الكابشن ✨")

    # Get best resolution photo
    photo = update.message.photo[-1]
    tg_file = await photo.get_file()
    bio = BytesIO()
    await tg_file.download_to_memory(out=bio)
    image_bytes = bio.getvalue()

    try:
        image_url = _upload_to_imgbb(image_bytes)
        caption = _generate_ai_caption(image_url)

        scheduled_time = datetime.now(timezone.utc) + timedelta(minutes=BUFFER_MINUTES)
        scheduled_iso = scheduled_time.replace(microsecond=0).isoformat()

        ws = _get_sheet_ws()
        append_scheduled_post(
            ws,
            image_url=image_url,
            ai_caption=caption,
            scheduled_time_iso=scheduled_iso,
        )

        await update.message.reply_text(
            f"✅ Saved to queue. Will post in {BUFFER_MINUTES} mins unless edited.\n\n"
            f"🖼️ {image_url}\n"
            f"⏰ {scheduled_iso}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is missing")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
