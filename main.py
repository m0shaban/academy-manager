import os
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import requests
from groq import Groq

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
    utc_now_iso,
)


GROQ_API_KEY = os.environ.get("GROQ_API_KEY_4", "").strip()
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN", "").strip()

GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "").strip()
GOOGLE_SHEET_WORKSHEET = os.environ.get("GOOGLE_SHEET_WORKSHEET", "Buffer").strip() or "Buffer"

BUFFER_MINUTES = int(os.environ.get("BUFFER_MINUTES", "30") or "30")
PREFILL_HOURS = int(os.environ.get("PREFILL_HOURS", "6") or "6")
INTERVAL_SECONDS = int(os.environ.get("PUBLISHER_INTERVAL_SECONDS", "60") or "60")

ACTIVE_HOURS_RAW = os.environ.get("ACTIVE_HOURS", "").strip()
if ACTIVE_HOURS_RAW:
    ACTIVE_HOURS = [int(x) for x in ACTIVE_HOURS_RAW.split(",") if x.strip().isdigit()]
else:
    ACTIVE_HOURS = []


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _next_available_slot(now_utc: datetime) -> datetime:
    # Always apply buffer first.
    candidate = now_utc + timedelta(minutes=max(BUFFER_MINUTES, 0))

    if not ACTIVE_HOURS:
        return candidate

    # Move forward to next hour that is allowed.
    for _ in range(0, 72):
        if candidate.hour in ACTIVE_HOURS:
            return candidate
        candidate = (candidate + timedelta(hours=1)).replace(minute=0, second=0)
    return now_utc + timedelta(minutes=max(BUFFER_MINUTES, 0))


def _get_sheet():
    if not GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID not set")

    svc = load_service_account_info_from_env()
    if not svc:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON/FILE not set")

    client = make_gspread_client(svc)
    ws = open_worksheet(client, SheetConfig(sheet_id=GOOGLE_SHEET_ID, worksheet=GOOGLE_SHEET_WORKSHEET))
    header = ensure_headers(ws)
    return ws, header


def _pollinations_url(prompt_en: str) -> str:
    encoded = urllib.parse.quote(prompt_en.strip(), safe="")
    return f"https://image.pollinations.ai/prompt/{encoded}"


def _generate_image_prompt_en(groq: Optional[Groq]) -> str:
    if not groq:
        return "Cinematic photo of kids martial arts training in Cairo, golden hour, energetic, high detail"

    prompt = (
        "Write ONE short English image prompt (8-18 words) for a cinematic sports/martial-arts academy scene. "
        "Must be safe-for-work, no violence, suitable for Facebook. Avoid copyrighted characters."
    )
    res = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=80,
        temperature=0.9,
    )
    return (res.choices[0].message.content or "").strip().strip('"')


def _generate_ar_caption(groq: Optional[Groq], prompt_en: str) -> str:
    if not groq:
        return "🥋 تدريب النهارده نار! جاهزين تبدأوا؟ احجز مكانك دلوقتي 💪📞"

    prompt = (
        "اكتب كابشن فيسبوك عربي مصري (عامية) عن صورة تدريب في أكاديمية رياضية. "
        "الكابشن 2-4 سطور، تحفيزي، وفيه CTA للحجز، وإيموجيز بسيطة. "
        f"وصف الصورة (بالإنجليزية): {prompt_en}"
    )
    res = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250,
        temperature=0.85,
    )
    return (res.choices[0].message.content or "").strip()


def _post_to_facebook(caption: str, image_url: Optional[str]) -> Tuple[bool, str]:
    if not PAGE_ACCESS_TOKEN:
        return False, "PAGE_ACCESS_TOKEN not set"

    params = {"access_token": PAGE_ACCESS_TOKEN}

    # Prefer photo publishing when image_url is available
    if image_url:
        try:
            url = "https://graph.facebook.com/v18.0/me/photos"
            data = {"url": image_url, "caption": caption}
            r = requests.post(url, params=params, json=data, timeout=30)
            if r.status_code == 200:
                return True, "ok"
        except Exception:
            pass

    # Fallback: feed post
    try:
        url = "https://graph.facebook.com/v18.0/me/feed"
        data: dict = {"message": caption}
        if image_url:
            data["link"] = image_url
        r = requests.post(url, params=params, json=data, timeout=30)
        r.raise_for_status()
        return True, "ok"
    except Exception as e:
        return False, str(e)


def tick_once() -> None:
    groq = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

    ws, header = _get_sheet()
    rows = list_rows(ws)

    # 1) Publish due posts (oldest first)
    due = find_due_scheduled(rows)
    if due:
        item = due[0]
        row_number = int(item.get("_row_number") or 0)
        caption = str(item.get("AI_Caption") or "").strip()
        image_url = str(item.get("Image_URL") or "").strip() or None

        ok, err = _post_to_facebook(caption, image_url)
        if ok:
            from gsheets_cms import update_fields

            update_fields(ws, row_number, header, {"Status": "Posted"})
        else:
            from gsheets_cms import update_fields

            update_fields(ws, row_number, header, {"Status": "Failed"})
        return

    # 2) Prefill AI-generated content if no scheduled posts in next PREFILL_HOURS
    now = _utc_now()
    window_end = now + timedelta(hours=max(PREFILL_HOURS, 1))
    if has_scheduled_within(rows, start=now, end=window_end):
        return

    prompt_en = _generate_image_prompt_en(groq)
    img_url = _pollinations_url(prompt_en)
    caption_ar = _generate_ar_caption(groq, prompt_en)

    scheduled_time = _next_available_slot(now)
    scheduled_iso = scheduled_time.isoformat()

    append_row(
        ws,
        header,
        {
            "Timestamp": utc_now_iso(),
            "Image_URL": img_url,
            "AI_Caption": caption_ar,
            "Status": "Scheduled",
            "Scheduled_Time": scheduled_iso,
            "Source": "AI_Generated",
        },
    )


def main() -> None:
    while True:
        try:
            tick_once()
        except Exception as e:
            print("tick error:", str(e))
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
