import streamlit as st

import requests
from typing import Optional, Tuple

from gsheets_connection import GoogleSheetsConnection
from gsheets_cms import delete_row, update_fields


st.set_page_config(page_title="CMS Buffer", layout="wide")


def _get_setting(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, default) or default)
    except Exception:
        return default


PAGE_ACCESS_TOKEN = _get_setting("PAGE_ACCESS_TOKEN", "")


def _post_to_facebook(caption: str, image_url: Optional[str]) -> Tuple[bool, str]:
    if not PAGE_ACCESS_TOKEN:
        return False, "Missing PAGE_ACCESS_TOKEN in Streamlit secrets"

    params = {"access_token": PAGE_ACCESS_TOKEN}

    if image_url:
        try:
            img_resp = requests.get(image_url, timeout=30)
            img_resp.raise_for_status()
            content_type = img_resp.headers.get("content-type", "image/jpeg")
            files = {"source": ("image", img_resp.content, content_type)}
            data = {"caption": caption}
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
            data = {"url": image_url, "caption": caption}
            r = requests.post(url, params=params, json=data, timeout=30)
            if r.status_code == 200:
                return True, "ok"
        except Exception:
            pass

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


st.title("🗂️ Buffer CMS (Google Sheets)")
st.caption("مراجعة + تعديل + اعتماد المنشورات قبل النشر")
st.info(
    "أوامر تيليجرام للأدمن: /queue, /post <row>, /delete <row>, /caption <row> <text>, /status",
    icon="💬",
)

conn = st.connection("gsheets", type=GoogleSheetsConnection)

ws, header = conn.worksheet()
rows = conn.read(ttl=0) or []

pending_rows = [
    r
    for r in rows
    if str(r.get("Status", "")).strip().lower() == "scheduled"
]

pending_rows.sort(key=lambda r: str(r.get("Scheduled_Time") or ""))

st.markdown("### ⏳ Pending (Scheduled)")

if not pending_rows:
    st.success("✅ لا يوجد منشورات معلّقة")
    st.stop()

for row in pending_rows:
    row_number = int(row.get("_row_number") or 0)
    img_url = str(row.get("Image_URL") or "").strip()
    sched = str(row.get("Scheduled_Time") or "").strip()
    source = str(row.get("Source") or "").strip()
    caption = str(row.get("AI_Caption") or "").strip()

    with st.container(border=True):
        st.markdown(f"**Time:** {sched} • **Source:** {source} • **Row:** {row_number or 'N/A'}")
        if img_url:
            st.image(img_url, use_container_width=True)

        new_caption = st.text_area(
            "Caption",
            value=caption,
            height=120,
            key=f"cap_{row_number}_{sched}",
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("💾 Save Updates", key=f"save_{row_number}_{sched}"):
                if not row_number:
                    st.error("لم أستطع تحديد رقم الصف في الشيت.")
                else:
                    update_fields(ws, row_number, header, {"AI_Caption": new_caption})
                    st.success("✅ تم الحفظ")
                    st.rerun()

        with c2:
            if st.button("🚀 Post Now", key=f"post_{row_number}_{sched}"):
                if not row_number:
                    st.error("لم أستطع تحديد رقم الصف في الشيت.")
                else:
                    ok, err = _post_to_facebook(new_caption, img_url or None)
                    if ok:
                        update_fields(ws, row_number, header, {"Status": "Posted", "AI_Caption": new_caption})
                        st.success("✅ تم النشر")
                        st.rerun()
                    else:
                        update_fields(ws, row_number, header, {"Status": "Failed"})
                        st.error(f"❌ فشل النشر: {err}")

        with c3:
            if st.button("🗑️ Delete", key=f"del_{row_number}_{sched}"):
                if not row_number:
                    st.error("لم أستطع تحديد رقم الصف في الشيت.")
                else:
                    delete_row(ws, row_number)
                    st.success("✅ تم الحذف")
                    st.rerun()
