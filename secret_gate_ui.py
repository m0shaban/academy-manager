"""Secret gate UI (admin-only) for voucher generation.

Important: UI gates are for obfuscation, not real security.
Real protection is enforced server-side via ADMIN_TOKEN in webhook.py.
"""

from __future__ import annotations

import streamlit as st
import requests


def _hide_sidebar_nav():
    st.markdown(
        """
<style>
[data-testid="stSidebarNav"]{display:none !important;}
[data-testid="stSidebar"]{display:none !important;}
button[kind="header"]{display:none !important;}
</style>
""",
        unsafe_allow_html=True,
    )


def _inject_styles():
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
*{font-family:'Cairo',sans-serif !important;}
.stApp,.main,.block-container{direction:rtl !important;text-align:right !important;}

h1,h2,h3,p,label,span,div{direction:rtl !important;text-align:right !important;line-height:1.8 !important;letter-spacing:0.5px !important;}
.stTextInput input,.stNumberInput input{direction:rtl !important;text-align:right !important;font-size:1.05rem !important;padding:10px 15px !important;}
.stTextInput label,.stNumberInput label,.stSelectbox label{font-size:1rem !important;font-weight:600 !important;margin-bottom:8px !important;display:block !important;}
.stButton>button{width:100%;font-size:1.15rem;padding:0.75rem;margin-top:10px;}

.gate-box{background:linear-gradient(135deg,#2d3436,#636e72);padding:26px;border-radius:20px;text-align:center !important;color:#fff;margin:18px 0;border:3px solid #ffeaa7;}
.gate-box h2{text-align:center !important;margin-bottom:12px;}

.success-gate{background:linear-gradient(135deg,#00b894,#00cec9);padding:16px;border-radius:15px;text-align:center !important;color:#fff;margin:14px 0;}
.locked-gate{background:linear-gradient(135deg,#d63031,#e17055);padding:16px;border-radius:15px;text-align:center !important;color:#fff;margin:14px 0;}
.admin-header{background:linear-gradient(135deg,#6c5ce7,#a29bfe);padding:26px;border-radius:20px;text-align:center !important;color:#fff;margin-bottom:22px;}

.progress-bar{display:flex;justify-content:center;gap:10px;margin:16px 0;}
.progress-step{width:46px;height:46px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.4rem;}
.step-locked{background:#636e72;border:2px solid #b2bec3;}
.step-unlocked{background:#00b894;border:2px solid #00cec9;}

.code-box{background:#2d3436;color:#00ff88;padding:12px;border-radius:10px;font-family:'Courier New',monospace !important;direction:ltr !important;text-align:left !important;margin:5px 0;font-size:1.05rem;}
</style>
""",
        unsafe_allow_html=True,
    )


def _init_state():
    for key in ("gate1_passed", "gate2_passed", "gate3_passed", "gate4_passed"):
        if key not in st.session_state:
            st.session_state[key] = False


def _show_progress():
    st.markdown(
        f"""
<div class="progress-bar">
  <div class="progress-step {'step-unlocked' if st.session_state.gate1_passed else 'step-locked'}">{'✅' if st.session_state.gate1_passed else '🔒'}</div>
  <div class="progress-step {'step-unlocked' if st.session_state.gate2_passed else 'step-locked'}">{'✅' if st.session_state.gate2_passed else '🔒'}</div>
  <div class="progress-step {'step-unlocked' if st.session_state.gate3_passed else 'step-locked'}">{'✅' if st.session_state.gate3_passed else '🔒'}</div>
  <div class="progress-step {'step-unlocked' if st.session_state.gate4_passed else 'step-locked'}">{'✅' if st.session_state.gate4_passed else '🔒'}</div>
</div>
""",
        unsafe_allow_html=True,
    )


def _reset_gates():
    st.session_state.gate1_passed = False
    st.session_state.gate2_passed = False
    st.session_state.gate3_passed = False
    st.session_state.gate4_passed = False


def _admin_token_header() -> dict:
    token = st.secrets.get("ADMIN_TOKEN", "")
    return {"X-Admin-Token": token} if token else {}


def render_secret_gate(backend_url: str, *, standalone: bool = False) -> None:
    """Render the secret gate + voucher generation UI.

    - `backend_url`: Render webhook base URL.
    - `standalone`: True when used as a dedicated Streamlit page.
    """

    if standalone:
        _hide_sidebar_nav()

    _inject_styles()
    _init_state()

    st.markdown(
        """
<div class="gate-box">
  <h2>🏰 البوابة السرية للأكواد 🏰</h2>
  <p>4 بوابات… والأسئلة كلها تمويه (الإجابات مش باينة خالص).</p>
</div>
""",
        unsafe_allow_html=True,
    )

    _show_progress()

    # Gate 1
    if not st.session_state.gate1_passed:
        st.markdown(
            """
<div class="locked-gate">
  <h3>🚪 البوابة الأولى</h3>
  <p>سؤال تمويهي رقم 1: اكتب اسم أول مدرس انت حبيته (من غير مسافات).</p>
</div>
""",
            unsafe_allow_html=True,
        )
        value = st.text_input(
            "🗝️ إجابتك:", type="password", key="gate1", placeholder="(سؤال تمويه)"
        )
        if st.button("فتح", key="btn_gate1", use_container_width=True):
            if value == "سمسم":
                st.session_state.gate1_passed = True
                st.rerun()
            else:
                st.error("❌ غلط.")
        return

    # Gate 2
    if not st.session_state.gate2_passed:
        st.markdown(
            """
<div class="success-gate"><h3>✅ البوابة الأولى مفتوحة</h3></div>
<div class="locked-gate">
  <h3>🚪 البوابة الثانية</h3>
  <p>سؤال تمويهي رقم 2: اكتب اسم أول لعبة على موبايلك (3 حروف بالضبط).</p>
</div>
""",
            unsafe_allow_html=True,
        )
        value = st.text_input("🧩 إجابتك:", key="gate2", placeholder="(سؤال تمويه)")
        if st.button("فتح", key="btn_gate2", use_container_width=True):
            if value == "بلح":
                st.session_state.gate2_passed = True
                st.rerun()
            else:
                st.error("❌ غلط.")
        return

    # Gate 3
    if not st.session_state.gate3_passed:
        st.markdown(
            """
<div class="success-gate"><h3>✅ بوابتين مفتوحين</h3></div>
<div class="locked-gate">
  <h3>🚪 البوابة الثالثة</h3>
  <p>سؤال تمويهي رقم 3: اكتب اسم كارتون قديم (من غير مسافات).</p>
</div>
""",
            unsafe_allow_html=True,
        )
        value = st.text_input("🧩 إجابتك:", key="gate3", placeholder="(سؤال تمويه)")
        if st.button("فتح", key="btn_gate3", use_container_width=True):
            if value == "طرح":
                st.session_state.gate3_passed = True
                st.rerun()
            else:
                st.error("❌ غلط.")
        return

    # Gate 4
    if not st.session_state.gate4_passed:
        st.markdown(
            """
<div class="success-gate"><h3>✅ 3 بوابات مفتوحة</h3></div>
<div class="locked-gate">
  <h3>🚪 البوابة الأخيرة</h3>
  <p>سؤال تمويهي رقم 4: اكتب اسم أكلة مفضلة (3 حروف).</p>
</div>
""",
            unsafe_allow_html=True,
        )
        value = st.text_input("🧩 إجابتك:", key="gate4", placeholder="(سؤال تمويه)")
        if st.button("فتح", key="btn_gate4", use_container_width=True):
            if value == "موز":
                st.session_state.gate4_passed = True
                st.rerun()
            else:
                st.error("❌ غلط.")
        return

    # Vault
    st.markdown(
        """
<div class="admin-header">
  <h1>🎉 وصلت لغرفة الكنز 🎉</h1>
  <p>لو مش إنت المدير… اقفل الصفحة بهدوء 😄</p>
</div>
""",
        unsafe_allow_html=True,
    )

    cols = st.columns([4, 1])
    with cols[1]:
        if st.button("🚪 خروج", key="logout"):
            _reset_gates()
            st.rerun()

    count = st.number_input(
        "📊 عدد الأكواد", min_value=1, max_value=200, value=10, step=1
    )
    duration = st.selectbox(
        "📅 مدة الاشتراك",
        options=[7, 14, 30, 60, 90, 180, 365],
        index=2,
        format_func=lambda x: (
            f"{x} يوم" if x < 30 else f"{x // 30} شهر" if x % 30 == 0 else f"{x} يوم"
        ),
    )

    if not st.secrets.get("ADMIN_TOKEN", ""):
        st.error(
            "⚠️ لازم تضيف ADMIN_TOKEN في Streamlit Secrets عشان التوليد يشتغل بشكل آمن."
        )
        return

    if st.button("🎫 توليد الآن", type="primary", use_container_width=True):
        with st.spinner("⏳ جاري التوليد..."):
            try:
                resp = requests.post(
                    f"{backend_url.rstrip('/')}/gen-vouchers",
                    headers=_admin_token_header(),
                    json={"count": int(count), "duration_days": int(duration)},
                    timeout=30,
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    codes = payload.get("codes", [])
                    st.success(f"✅ تم توليد {len(codes)} كود")
                    all_codes = "\n".join(codes)
                    st.code(all_codes, language=None)
                    st.download_button(
                        "📥 تحميل TXT",
                        data=all_codes,
                        file_name=f"codes_{duration}days_{len(codes)}.txt",
                        mime="text/plain",
                    )
                    with st.expander("📜 عرض فردي"):
                        for i, code in enumerate(codes, 1):
                            st.markdown(
                                f"<div class='code-box'>{i}. {code}</div>",
                                unsafe_allow_html=True,
                            )
                elif resp.status_code in (401, 403):
                    st.error("❌ غير مصرح.")
                else:
                    try:
                        msg = resp.json().get("message", "فشل")
                    except Exception:
                        msg = "فشل"
                    st.error(f"❌ {msg}")
            except Exception:
                st.error("❌ تعذر الاتصال بالسيرفر.")
