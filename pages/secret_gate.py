"""
صفحة توليد أكواد الاشتراك (Vouchers)
محمية بـ 4 طبقات أمان فكاهية 🍌
"""

import streamlit as st
import requests

# Page config - Hidden from navigation
st.set_page_config(
    page_title="🔒 البوابة السرية",
    page_icon="🔐",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Hide this page from sidebar navigation
hide_page_style = """
<style>
    [data-testid="stSidebarNav"] {
        display: none !important;
    }
    
    /* Hide sidebar completely */
    [data-testid="stSidebar"] {
        display: none !important;
    }
    
    /* Remove sidebar toggle button */
    button[kind="header"] {
        display: none !important;
    }
</style>
"""
st.markdown(hide_page_style, unsafe_allow_html=True)

# RTL Support + Fixed text overlap
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    
    * {
        font-family: 'Cairo', sans-serif !important;
    }
    
    .stApp, .main, .block-container {
        direction: rtl !important;
        text-align: right !important;
    }
    
    /* Fix text overlap */
    h1, h2, h3, p, label, span, div {
        direction: rtl !important;
        text-align: right !important;
        line-height: 1.8 !important;
        letter-spacing: 0.5px !important;
    }
    
    /* Fix input fields */
    .stTextInput input, .stNumberInput input {
        direction: rtl !important;
        text-align: right !important;
        font-size: 1.1rem !important;
        padding: 10px 15px !important;
    }
    
    /* Fix labels */
    .stTextInput label, .stNumberInput label, .stSelectbox label {
        font-size: 1rem !important;
        font-weight: 600 !important;
        margin-bottom: 8px !important;
        display: block !important;
    }
    
    .stButton > button {
        width: 100%;
        font-size: 1.2rem;
        padding: 0.75rem;
        margin-top: 10px;
    }
    
    .gate-box {
        background: linear-gradient(135deg, #2d3436, #636e72);
        padding: 30px;
        border-radius: 20px;
        text-align: center !important;
        color: white;
        margin: 20px 0;
        border: 3px solid #ffeaa7;
    }
    
    .gate-box h2 {
        text-align: center !important;
        margin-bottom: 20px;
    }
    
    .success-gate {
        background: linear-gradient(135deg, #00b894, #00cec9);
        padding: 20px;
        border-radius: 15px;
        text-align: center !important;
        color: white;
        margin: 15px 0;
        animation: pulse 1s ease-in-out;
    }
    
    @keyframes pulse {
        0% { transform: scale(0.95); opacity: 0; }
        50% { transform: scale(1.02); }
        100% { transform: scale(1); opacity: 1; }
    }
    
    .locked-gate {
        background: linear-gradient(135deg, #d63031, #e17055);
        padding: 20px;
        border-radius: 15px;
        text-align: center !important;
        color: white;
        margin: 15px 0;
    }
    
    .hint-box {
        background: #74b9ff;
        color: #2d3436;
        padding: 15px;
        border-radius: 10px;
        margin: 15px 0;
        font-size: 0.9rem;
    }
    
    .code-box {
        background: #2d3436;
        color: #00ff88;
        padding: 15px;
        border-radius: 10px;
        font-family: 'Courier New', monospace !important;
        direction: ltr !important;
        text-align: left !important;
        margin: 5px 0;
        font-size: 1.1rem;
    }
    
    .admin-header {
        background: linear-gradient(135deg, #6c5ce7, #a29bfe);
        padding: 30px;
        border-radius: 20px;
        text-align: center !important;
        color: white;
        margin-bottom: 30px;
    }
    
    .progress-bar {
        display: flex;
        justify-content: center;
        gap: 10px;
        margin: 20px 0;
    }
    
    .progress-step {
        width: 50px;
        height: 50px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.5rem;
        transition: all 0.3s;
    }
    
    .step-locked {
        background: #636e72;
        border: 2px solid #b2bec3;
    }
    
    .step-unlocked {
        background: #00b894;
        border: 2px solid #00cec9;
        animation: bounce 0.5s ease;
    }
    
    @keyframes bounce {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-10px); }
    }
</style>
""", unsafe_allow_html=True)

# Initialize session states
if "gate1_passed" not in st.session_state:
    st.session_state.gate1_passed = False
if "gate2_passed" not in st.session_state:
    st.session_state.gate2_passed = False
if "gate3_passed" not in st.session_state:
    st.session_state.gate3_passed = False
if "gate4_passed" not in st.session_state:
    st.session_state.gate4_passed = False
if "all_gates_passed" not in st.session_state:
    st.session_state.all_gates_passed = False

# Backend URL
BACKEND_URL = st.secrets.get("BACKEND_URL", "https://your-render-app.onrender.com")

def show_progress():
    """عرض شريط التقدم"""
    st.markdown(f"""
    <div class="progress-bar">
        <div class="progress-step {'step-unlocked' if st.session_state.gate1_passed else 'step-locked'}">
            {'✅' if st.session_state.gate1_passed else '🔒'}
        </div>
        <div class="progress-step {'step-unlocked' if st.session_state.gate2_passed else 'step-locked'}">
            {'✅' if st.session_state.gate2_passed else '🔒'}
        </div>
        <div class="progress-step {'step-unlocked' if st.session_state.gate3_passed else 'step-locked'}">
            {'✅' if st.session_state.gate3_passed else '🔒'}
        </div>
        <div class="progress-step {'step-unlocked' if st.session_state.gate4_passed else 'step-locked'}">
            {'✅' if st.session_state.gate4_passed else '🔒'}
        </div>
    </div>
    """, unsafe_allow_html=True)

def reset_gates():
    """إعادة تعيين البوابات"""
    st.session_state.gate1_passed = False
    st.session_state.gate2_passed = False
    st.session_state.gate3_passed = False
    st.session_state.gate4_passed = False
    st.session_state.all_gates_passed = False

# Main Header
st.markdown("""
<div class="gate-box">
    <h2>🏰 البوابة السرية للأكواد 🏰</h2>
    <p>4 بوابات أمان يجب اختراقها للوصول لغرفة الكنز!</p>
</div>
""", unsafe_allow_html=True)

show_progress()

# ========== GATE 1: سمسم ==========
if not st.session_state.gate1_passed:
    st.markdown("""
    <div class="locked-gate">
        <h3>🚪 البوابة الأولى</h3>
        <p>قل الكلمة السحرية لعلي بابا...</p>
    </div>
    """, unsafe_allow_html=True)
    
    gate1_input = st.text_input("🗝️ الكلمة السحرية:", type="password", key="gate1", placeholder="افتح يا...")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🚀 فتح البوابة الأولى", key="btn_gate1", use_container_width=True):
            if gate1_input == "سمسم":
                st.session_state.gate1_passed = True
                st.balloons()
                st.rerun()
            else:
                st.error("❌ أممم... علي بابا غير موافق!")
    with col2:
        if st.button("💡", key="hint1"):
            st.info("💡 تلميح: علي بابا كان بيقول 'افتح يا ___'")

# ========== GATE 2: بلح ==========
elif not st.session_state.gate2_passed:
    st.markdown("""
    <div class="success-gate">
        <h3>✅ البوابة الأولى مفتوحة!</h3>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="locked-gate">
        <h3>🚪 البوابة الثانية</h3>
        <p>🌴 فاكهة من النخل، حلوة وبنية...</p>
    </div>
    """, unsafe_allow_html=True)
    
    gate2_input = st.text_input("🌴 اسم الفاكهة:", key="gate2", placeholder="فاكهة من النخل...")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🚀 فتح البوابة الثانية", key="btn_gate2", use_container_width=True):
            if gate2_input == "بلح":
                st.session_state.gate2_passed = True
                st.balloons()
                st.rerun()
            else:
                st.error("❌ لأ مش دي... فكر في النخل!")
    with col2:
        if st.button("💡", key="hint2"):
            st.info("💡 تلميح: ب___ (3 حروف)")

# ========== GATE 3: طرح ==========
elif not st.session_state.gate3_passed:
    st.markdown("""
    <div class="success-gate">
        <h3>✅ البوابتين الأولى والثانية مفتوحتين!</h3>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="locked-gate">
        <h3>🚪 البوابة الثالثة</h3>
        <p>➖ عملية حسابية عكس الجمع...</p>
    </div>
    """, unsafe_allow_html=True)
    
    gate3_input = st.text_input("➖ اسم العملية:", key="gate3", placeholder="عكس الجمع...")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🚀 فتح البوابة الثالثة", key="btn_gate3", use_container_width=True):
            if gate3_input == "طرح":
                st.session_state.gate3_passed = True
                st.balloons()
                st.rerun()
            else:
                st.error("❌ لأ... 5 - 3 = ؟ العملية دي اسمها إيه؟")
    with col2:
        if st.button("💡", key="hint3"):
            st.info("💡 تلميح: ط___ (3 حروف)")

# ========== GATE 4: موز ==========
elif not st.session_state.gate4_passed:
    st.markdown("""
    <div class="success-gate">
        <h3>✅ 3 بوابات مفتوحة! باقي واحدة بس!</h3>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="locked-gate">
        <h3>🚪 البوابة الأخيرة</h3>
        <p>🍌 فاكهة صفراء بياكلها القرود...</p>
    </div>
    """, unsafe_allow_html=True)
    
    gate4_input = st.text_input("🍌 اسم الفاكهة:", key="gate4", placeholder="القرود بتحبها...")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🚀 فتح البوابة الأخيرة!", key="btn_gate4", use_container_width=True):
            if gate4_input == "موز":
                st.session_state.gate4_passed = True
                st.session_state.all_gates_passed = True
                st.balloons()
                st.snow()
                st.rerun()
            else:
                st.error("❌ القرد زعل منك! 🐵")
    with col2:
        if st.button("💡", key="hint4"):
            st.info("💡 تلميح: م___ (3 حروف) 🍌")

# ========== ALL GATES PASSED - VOUCHER GENERATION ==========
else:
    st.markdown("""
    <div class="admin-header">
        <h1>🎉 مبروك! وصلت لغرفة الكنز! 🎉</h1>
        <p>🎫 لوحة توليد الأكواد - أكاديمية أبطال أكتوبر</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Logout button
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🚪 خروج وقفل البوابات"):
            reset_gates()
            st.rerun()
    
    st.markdown("---")
    
    # Voucher Generation Form
    st.markdown("### ⚙️ إعدادات توليد الأكواد")
    
    col1, col2 = st.columns(2)
    
    with col1:
        count = st.number_input(
            "📊 عدد الأكواد:",
            min_value=1,
            max_value=100,
            value=10,
            step=1
        )
    
    with col2:
        duration = st.selectbox(
            "📅 مدة الاشتراك:",
            options=[7, 14, 30, 60, 90, 180, 365],
            format_func=lambda x: f"{x} يوم" if x < 30 else f"{x // 30} شهر" if x % 30 == 0 else f"{x} يوم",
            index=2
        )
    
    st.markdown("---")
    
    # Generate button
    if st.button("🎫 توليد الأكواد الآن", type="primary", use_container_width=True):
        with st.spinner("⏳ جاري توليد الأكواد..."):
            try:
                response = requests.post(
                    f"{BACKEND_URL}/gen-vouchers",
                    json={
                        "step1": "بلح",
                        "step2": "طرح",
                        "step3": "موز",
                        "count": count,
                        "duration_days": duration
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    codes = data.get("codes", [])
                    
                    st.markdown(f"""
                    <div class="success-gate">
                        <h3>✅ تم توليد {len(codes)} كود بنجاح!</h3>
                        <p>مدة كل كود: {duration} يوم</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Display codes
                    st.markdown("### 📋 الأكواد المولدة:")
                    
                    all_codes = "\n".join(codes)
                    st.code(all_codes, language=None)
                    
                    # Download button
                    st.download_button(
                        label="📥 تحميل الأكواد (TXT)",
                        data=all_codes,
                        file_name=f"vouchers_{duration}days_{count}codes.txt",
                        mime="text/plain"
                    )
                    
                    # Individual codes display
                    with st.expander("📜 عرض الأكواد بشكل فردي"):
                        for i, code in enumerate(codes, 1):
                            st.markdown(f"""
                            <div class="code-box">
                                {i}. {code}
                            </div>
                            """, unsafe_allow_html=True)
                            
                else:
                    error_msg = response.json().get("message", "خطأ غير معروف")
                    st.error(f"❌ فشل توليد الأكواد: {error_msg}")
                    
            except requests.exceptions.ConnectionError:
                st.error("❌ لا يمكن الاتصال بالسيرفر. تأكد من أن Backend يعمل على Render.")
                st.info(f"🔗 رابط السيرفر: {BACKEND_URL}")
                
            except Exception as e:
                st.error(f"❌ حدث خطأ: {str(e)}")
    
    # Manual generation (offline mode)
    st.markdown("---")
    with st.expander("🔧 توليد أكواد محلياً (بدون سيرفر)"):
        st.warning("⚠️ هذه الأكواد لن تُحفظ في قاعدة البيانات!")
        
        local_count = st.number_input("عدد الأكواد:", min_value=1, max_value=50, value=5, key="local_count")
        
        if st.button("توليد محلي", key="local_gen"):
            import random
            
            alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
            local_codes = ["".join(random.choice(alphabet) for _ in range(12)) for _ in range(local_count)]
            
            st.code("\n".join(local_codes))
            st.info("💡 لحفظ الأكواد في قاعدة البيانات، استخدم الطريقة العادية مع تشغيل السيرفر.")
    
    # Instructions
    st.markdown("---")
    st.markdown("""
    ### 📖 تعليمات الاستخدام:
    
    1. **اختر عدد الأكواد** المراد توليدها
    2. **اختر مدة الاشتراك** لكل كود
    3. **اضغط توليد** وانتظر
    4. **انسخ أو حمّل** الأكواد
    5. **وزّع الأكواد** على العملاء
    
    ---
    
    ### 🔑 كيف يستخدم العميل الكود؟
    
    يرسل رسالة للبوت على الماسنجر بالصيغة:
    ```
    تفعيل XXXX-XXXX-XXXX
    ```
    """)

# Reset button at bottom
st.markdown("---")
if st.button("🔄 إعادة تعيين كل البوابات", key="reset_all"):
    reset_gates()
    st.rerun()
