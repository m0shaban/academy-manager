"""
Smart Academy Manager - Streamlit Application
أكاديمية أبطال أكتوبر - نظام إدارة المحتوى الذكي
مع توليد الصور وتحليل RSS
"""

import streamlit as st
import json
import random
import requests
import base64
import os
import time
from pathlib import Path
from datetime import datetime
from io import BytesIO

# Load environment variables
# from dotenv import load_dotenv
# load_dotenv()

# Try to import optional libraries
try:
    from groq import Groq

    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import feedparser

    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

# --- Configuration ---
DATA_FILE = Path(__file__).parent / "academy_data.json"
# ENV_FILE = Path(__file__).parent / ".env" # No longer needed with Streamlit Secrets

# API Keys from Streamlit Secrets
# Ensure you have a .streamlit/secrets.toml file locally or secrets set up in Streamlit Cloud
try:
    GROQ_API_KEY = st.secrets.get("GROQ_API_KEY_4", "")
    NVIDIA_API_KEY = st.secrets.get("NVIDIA_API_KEY", "")
    IMGBB_API_KEY = st.secrets.get("IMGBB_API_KEY", "")
    PAGE_ACCESS_TOKEN = st.secrets.get("PAGE_ACCESS_TOKEN", "")
except FileNotFoundError:
    st.error("ملف secrets.toml غير موجود. يرجى إعداد أسرار Streamlit.")
    GROQ_API_KEY = ""
    NVIDIA_API_KEY = ""
    IMGBB_API_KEY = ""
    PAGE_ACCESS_TOKEN = ""


def post_to_facebook_page(message, access_token, image_url=None):
    """Post content to Facebook Page Feed (Robust Mode)."""
    if not access_token:
        return None, "❌ لم يتم العثور على Page Access Token"

    params = {"access_token": access_token}

    # محاولة 1: النشر كصورة (شكل أفضل)
    if image_url:
        try:
            url = f"https://graph.facebook.com/v18.0/me/photos"
            data = {"url": image_url, "caption": message}
            response = requests.post(url, params=params, json=data, timeout=30)

            # إذا نجح، ارجع فوراً
            if response.status_code == 200:
                return response.json(), None
            else:
                print(
                    f"⚠️ فشل نشر الصورة مباشرة ({response.status_code})، جاري المحاولة كرابط..."
                )
        except Exception as e:
            print(f"⚠️ خطأ في نشر الصورة: {e}")

    # محاولة 2 (البديل المضمون): النشر كبوست عادي مع رابط
    url = f"https://graph.facebook.com/v18.0/me/feed"
    data = {"message": message}
    if image_url:
        data["link"] = image_url

    try:
        response = requests.post(url, params=params, json=data, timeout=30)
        response.raise_for_status()
        return response.json(), None
    except Exception as e:
        return None, f"❌ خطأ نهائي في النشر على فيسبوك: {str(e)}"


# --- Content Scenarios ---
CONTENT_SCENARIOS = {
    "💡 نصيحة تدريبية": {
        "icon": "💡",
        "image_prompt": "Professional photo of a {sport} coach teaching young students in a martial arts gym, warm lighting, motivational atmosphere",
        "prompt": """اكتب نصيحة تدريبية قصيرة ومفيدة عن رياضة {sport}.
النصيحة يجب أن تكون:
- عملية وقابلة للتطبيق
- مناسبة للمبتدئين والمتقدمين
- تشجع على الاستمرار في التدريب
اختم بتشجيع بسيط ودعوة للتدريب في الأكاديمية.""",
    },
    "🏆 قصة نجاح": {
        "icon": "🏆",
        "image_prompt": "Happy young child wearing {sport} uniform holding a trophy, proud parents in background, celebration scene",
        "prompt": """اكتب قصة نجاح ملهمة (خيالية) عن طفل بدأ التدريب في رياضة {sport}.
القصة يجب أن تبرز:
- التحول في شخصيته (الثقة، الانضباط)
- الفوائد الصحية والنفسية
- دور الأكاديمية في تطويره
اجعلها عاطفية ومحفزة للآباء للتسجيل.""",
    },
    "❓ هل تعلم": {
        "icon": "❓",
        "image_prompt": "Artistic infographic style image about {sport}, educational theme, colorful and engaging",
        "prompt": """اكتب معلومة مثيرة من نوع "هل تعلم" عن رياضة {sport}.
المعلومة يجب أن تكون:
- مفاجئة وجديدة
- علمية أو تاريخية
- تبرز فوائد الرياضة
اختم بسؤال تفاعلي يشجع على التعليق.""",
    },
    "📢 إعلان عرض": {
        "icon": "📢",
        "image_prompt": "Professional sports academy promotional banner, modern design, {sport} theme, sale announcement style",
        "prompt": """اكتب إعلان جذاب عن العروض الحالية للأكاديمية.
الإعلان يجب أن يكون:
- واضح ومباشر
- يخلق إحساس بالعجلة (عرض محدود)
- يتضمن السعر والموعد ورقم التواصل
استخدم إيموجي بشكل جذاب.""",
    },
    "🎯 دعوة للتسجيل": {
        "icon": "🎯",
        "image_prompt": "Group of happy children in {sport} uniforms practicing together in a modern gym, welcoming atmosphere",
        "prompt": """اكتب دعوة قوية للتسجيل في الأكاديمية لرياضة {sport}.
الدعوة يجب أن تتضمن:
- فوائد الرياضة للطفل
- الموعد والسعر
- أرقام التواصل والعنوان
اجعلها مقنعة للآباء المترددين.""",
    },
    "🧘 فوائد صحية": {
        "icon": "🧘",
        "image_prompt": "Healthy fit child doing {sport} stretching exercises, bright clean gym, wellness theme",
        "prompt": """اكتب عن الفوائد الصحية والنفسية لرياضة {sport} للأطفال.
تحدث عن:
- الفوائد البدنية (القوة، المرونة، التنسيق)
- الفوائد النفسية (الثقة، التركيز، الانضباط)
- الفوائد الاجتماعية (العمل الجماعي، الاحترام)
اختم بدعوة للاشتراك.""",
    },
    "👨‍👩‍👧 نصيحة للآباء": {
        "icon": "👨‍👩‍👧",
        "image_prompt": "Parent and child at {sport} practice, supportive family moment, encouraging atmosphere",
        "prompt": """اكتب نصيحة للآباء عن كيفية دعم طفلهم في ممارسة رياضة {sport}.
النصيحة يجب أن تشمل:
- كيفية تشجيع الطفل
- أهمية الصبر والاستمرارية
- دور الأسرة في النجاح الرياضي
اجعلها ودودة ومفيدة.""",
    },
    "📅 تذكير بالمواعيد": {
        "icon": "📅",
        "image_prompt": "Modern sports academy schedule board, {sport} icons, clean calendar design",
        "prompt": """اكتب تذكير ودي بمواعيد تدريب رياضة {sport} هذا الأسبوع.
التذكير يجب أن يكون:
- واضح وسهل القراءة
- يشجع على الالتزام
- يتضمن معلومات التواصل للاستفسار
اجعله حماسي ومشجع.""",
    },
}

# Sport translations for image prompts
SPORT_EN = {
    "كاراتيه": "karate",
    "كونغ فو": "kung fu",
    "كيك بوكسينج": "kickboxing",
    "جمباز": "gymnastics",
    "ملاكمة": "boxing",
    "تايكوندو": "taekwondo",
}

FALLBACK_IMAGES = [
    "https://i.ibb.co/xKGpF5sQ/469991854-122136396014386621-3832266993418146234-n.jpg",
    "https://images.unsplash.com/photo-1555597673-b21d5c935865?fm=jpg",
    "https://images.unsplash.com/photo-1516684991026-4c3032a2b4fd?fm=jpg",
    "https://images.unsplash.com/photo-1607031767898-5f319512ff1e?fm=jpg",
    "https://images.unsplash.com/photo-1738835935023-ebff4a85bc7e?fm=jpg",
    "https://images.unsplash.com/photo-1617627590804-1de3424fbf04?fm=jpg",
    "https://images.unsplash.com/photo-1764622078672-20f2cf5fcbc1?fm=jpg",
    "https://images.unsplash.com/photo-1711825044889-371d0cdf5fe1?fm=jpg",
    "https://images.unsplash.com/photo-1699464676033-150f72c9f030?fm=jpg",
    "https://images.unsplash.com/photo-1616447285757-3d0084ebd43b?fm=jpg",
    "https://images.unsplash.com/photo-1764622078439-245a43822a5c?fm=jpg",
]

# --- Coach Persona ---
COACH_SYSTEM_PROMPT = """أنت "كابتن عز غريب" - مدير ومدرب أكاديمية أبطال أكتوبر للفنون القتالية والجمباز.

شخصيتك:
🥋 مدرب محترف وخبير في الرياضات القتالية
💪 حماسي ومشجع، تحب تحفز الناس
😊 ودود ومرحب، بتتعامل مع الآباء باحترام
🎯 محترف ودقيق في المعلومات

أسلوبك في الكلام:
- تتحدث بالعربية المصرية العامية
- تستخدم إيموجي بشكل معتدل ومناسب
- تبدأ الرد بتحية ودودة
- تختم بدعوة للتواصل أو التسجيل
- تذكر العروض الحالية عند المناسبة

مهمتك:
1. الرد على استفسارات الآباء والمهتمين
2. تشجيع التسجيل في الأكاديمية
3. إبراز فوائد الرياضة للأطفال
4. تقديم معلومات دقيقة عن المواعيد والأسعار
5. الترويج للعروض الحالية

ملاحظات مهمة:
- دائماً اذكر رقم التواصل عند السؤال عن التسجيل
- شجع على زيارة الأكاديمية للتجربة
- أكد على أهمية الرياضة في بناء شخصية الطفل
- اذكر أن التدريب مناسب لجميع الأعمار من 4 سنوات"""


# --- Helper Functions ---
def load_academy_data():
    """Load academy data from JSON file."""
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_academy_data(data):
    """Save academy data to JSON file."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_ai_client(provider, api_key):
    """Get AI client based on provider selection."""
    if provider == "Groq" and GROQ_AVAILABLE:
        return Groq(api_key=api_key), "llama-3.3-70b-versatile"
    elif provider == "OpenAI" and OPENAI_AVAILABLE:
        return OpenAI(api_key=api_key), "gpt-4o-mini"
    return None, None


def generate_ai_response(client, model, system_prompt, user_message, academy_data):
    """Generate AI response with context injection."""
    phones = f"{academy_data.get('phone', '')}"
    if academy_data.get("phone_alt"):
        phones += f" أو {academy_data.get('phone_alt')}"

    context = f"""
📍 معلومات الأكاديمية:
- الاسم: {academy_data.get('academy_name', '')}
- المدير: {academy_data.get('manager', '')}
- العنوان: {academy_data.get('location', '')}
- خريطة جوجل: {academy_data.get('map_link', '')}
- فيسبوك: {academy_data.get('facebook', '')}
- الهاتف: {phones}

📅 المواعيد:
{json.dumps(academy_data.get('schedules', {}), ensure_ascii=False, indent=2)}

💰 الأسعار:
{json.dumps(academy_data.get('pricing', {}), ensure_ascii=False, indent=2)}

🎁 العروض الحالية:
{chr(10).join('- ' + offer for offer in academy_data.get('offers', []))}
"""

    full_system_prompt = f"{system_prompt}\n\n{context}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1024,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ خطأ في الاتصال بالـ API: {str(e)}"


# --- Image Functions ---
def fetch_rss_images(sport, data):
    """Fetch images from RSS feeds for a specific sport."""
    if not FEEDPARSER_AVAILABLE:
        return []

    content_sources = data.get("content_sources", {})
    sport_sources = content_sources.get(sport, [])

    images = []
    for source in sport_sources[:2]:  # Limit to 2 sources to avoid delays
        try:
            feed = feedparser.parse(source.get("url", ""))
            for entry in feed.entries[:3]:
                # Try to find images in entry
                if hasattr(entry, "media_content"):
                    for media in entry.media_content:
                        if "image" in media.get("type", ""):
                            images.append(
                                {
                                    "url": media.get("url"),
                                    "title": entry.get("title", ""),
                                    "source": source.get("name", ""),
                                }
                            )
                # Check for enclosures (common in RSS)
                if hasattr(entry, "enclosures"):
                    for enc in entry.enclosures:
                        if "image" in enc.get("type", ""):
                            images.append(
                                {
                                    "url": enc.get("href"),
                                    "title": entry.get("title", ""),
                                    "source": source.get("name", ""),
                                }
                            )
                # Check for images in content
                if hasattr(entry, "content"):
                    for content in entry.content:
                        if "<img" in content.get("value", ""):
                            import re

                            img_urls = re.findall(
                                r'src="([^"]+)"', content.get("value", "")
                            )
                            for img_url in img_urls:
                                if img_url.startswith("http"):
                                    images.append(
                                        {
                                            "url": img_url,
                                            "title": entry.get("title", ""),
                                            "source": source.get("name", ""),
                                        }
                                    )
        except Exception as e:
            continue

    return images[:5]  # Return max 5 images


def generate_nvidia_image(prompt, api_key):
    """Generate image using NVIDIA FLUX API."""
    if not api_key:
        return None, "❌ مفتاح NVIDIA API غير موجود"

    url = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux-schnell"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "prompt": prompt,
        "height": 1024,
        "width": 1024,
        "num_inference_steps": 4,
        "guidance_scale": 0.0,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()

        data = response.json()
        if "image" in data:
            # Decode base64 image
            return data["image"], None
        elif "artifacts" in data and len(data["artifacts"]) > 0:
            return data["artifacts"][0].get("base64"), None
        else:
            return None, "❌ لم يتم استلام صورة من API"

    except requests.exceptions.Timeout:
        return None, "⏱️ انتهى وقت الانتظار - حاول مرة أخرى"
    except requests.exceptions.RequestException as e:
        return None, f"❌ خطأ في الاتصال: {str(e)}"
    except Exception as e:
        return None, f"❌ خطأ غير متوقع: {str(e)}"


def upload_to_imgbb(image_base64, api_key):
    """Upload base64 image to ImgBB and return URL."""
    if not api_key:
        return None, "❌ مفتاح ImgBB API غير موجود"

    url = "https://api.imgbb.com/1/upload"

    payload = {
        "key": api_key,
        "image": image_base64,
        "name": f"academy_post_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    }

    try:
        response = requests.post(url, data=payload, timeout=30)
        response.raise_for_status()

        data = response.json()
        if data.get("success"):
            return data["data"]["url"], None
        else:
            return None, "❌ فشل رفع الصورة"

    except Exception as e:
        return None, f"❌ خطأ في رفع الصورة: {str(e)}"


# --- Page Configuration ---
st.set_page_config(
    page_title="أكاديمية أبطال أكتوبر v3.1",
    page_icon="🥋",
    layout="wide",
    initial_sidebar_state="expanded",
)
    st.markdown("### 🔗 روابط")
    if data.get("facebook"):
        st.markdown(f"[📘 فيسبوك]({data.get('facebook')})")
    if data.get("map_link"):
        st.markdown(f"[📍 الخريطة]({data.get('map_link')})")
    st.markdown(f"📞 **{data.get('phone', '')}**")

# --- Main Header ---
data = load_academy_data()
system_name = data.get('system_name', '🥋 مدير أكاديمية أبطال أكتوبر')
system_subtitle = data.get('system_subtitle', 'نظام ذكي لإدارة المحتوى مع توليد الصور 🖼️')

st.markdown(
    f"""
<div class="main-header">
    <h1 style="margin:0; font-size: 2.5rem;">{system_name}</h1>
    <p style="margin: 0.5rem 0 0 0; opacity: 0.9;">{system_subtitle}</p>
</div>
""",
    unsafe_allow_html=True,
)

# --- Navigation Tabs ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "✨ مولد المحتوى",
        "🤖 غرفة عمليات الكابتن (أتمتة)",
        "💬 بوت الردود",
        "📊 نظرة عامة",
        "⚙️ إعدادات النظام"
    ]
)

# ========================================
# TAB 1: Content Generator
# ========================================
with tab1:
    st.markdown("## ✨ مولد المحتوى الذكي مع الصور")
    st.markdown("المنشور يطلع جاهز بالنص والصورة - انسخ وانشر مباشرة! 🚀")

    data = load_academy_data()
    sports = list(data.get("schedules", {}).keys())

    # Scenario Selection
    st.markdown("### 🎯 اختر نوع المحتوى")

    cols = st.columns(4)
    scenarios_list = list(CONTENT_SCENARIOS.keys())
    for i, scenario in enumerate(scenarios_list):
        with cols[i % 4]:
            if st.button(scenario, key=f"scenario_{i}", use_container_width=True):
                st.session_state.selected_scenario = scenario

    current_scenario = st.session_state.get("selected_scenario", scenarios_list[0])

    st.markdown("---")

    # Configuration Row
    col1, col2 = st.columns([1, 1])

    with col1:
        selected_sport = st.selectbox("🏋️ اختر الرياضة", ["عشوائي"] + sports)

    with col2:
        include_cta = st.checkbox("📞 تضمين CTA", value=True)

    st.markdown(f"**📝 النوع المختار:** {current_scenario}")

    # Generate Button
    if st.button("✨ توليد المنشور الكامل", type="primary", use_container_width=True):
        if not groq_key:
            st.error("❌ يرجى إدخال Groq API Key")
        else:
            chosen_sport = (
                random.choice(sports) if selected_sport == "عشوائي" else selected_sport
            )
            chosen_sport_en = SPORT_EN.get(chosen_sport, "martial arts")

            # Progress
            progress = st.progress(0)
            status = st.empty()

            # Step 1: Generate Text
            status.info("📝 جاري كتابة المنشور...")
            progress.progress(20)

            scenario_data = CONTENT_SCENARIOS[current_scenario]
            base_prompt = scenario_data["prompt"].format(sport=chosen_sport)

            cta_info = ""
            if include_cta:
                cta_info = f"""

في نهاية المنشور، أضف دعوة للتواصل:
- رقم التواصل: {data.get('phone', '')} أو {data.get('phone_alt', '')}
- العنوان: {data.get('location', '')}
"""

            full_prompt = f"""{base_prompt}

معلومات الرياضة:
- الموعد: {data.get('schedules', {}).get(chosen_sport, ['غير محدد'])[0]}
- السعر: {data.get('pricing', {}).get(chosen_sport, 'غير محدد')}

العروض الحالية:
{chr(10).join('- ' + o for o in data.get('offers', []))}
{cta_info}

اكتب المنشور باللغة العربية المصرية، استخدم إيموجي بشكل جذاب.
4-6 جمل فقط."""

            client, model = get_ai_client("Groq", groq_key)
            if client:
                post_text = generate_ai_response(
                    client, model, COACH_SYSTEM_PROMPT, full_prompt, data
                )
            else:
                post_text = "❌ فشل توليد النص"

            progress.progress(50)

            # Step 2: Get Image
            image_url = None

            status.info("📰 جاري البحث عن صور من المصادر...")
            progress.progress(70)

            rss_images = fetch_rss_images(chosen_sport, data)

            if rss_images:
                # Show image options
                st.session_state.rss_images = rss_images
                st.session_state.post_text = post_text
                st.session_state.chosen_sport = chosen_sport
                st.session_state.image_url = rss_images[0][
                    "url"
                ]  # Default to first RSS image
            else:
                st.warning(
                    "⚠️ لم يتم العثور على صور حديثة في المصادر، سيتم استخدام صورة احتياطية."
                )
                fb_img = random.choice(FALLBACK_IMAGES)
                st.session_state.image_url = fb_img
                st.session_state.post_text = post_text # Save the text!
                st.image(fb_img, caption="صورة احتياطية (من المجموعة)", width=300)

            progress.progress(100)
            status.success("✅ تم!")

            # Save to session state to display outside the button loop
            st.session_state.post_generated = True

    # Display Results (Outside the button loop to persist)
    if st.session_state.get("post_generated") and st.session_state.get("post_text"):
        st.markdown("---")
        st.markdown("### 📝 المنشور الجاهز:")
        st.markdown(
            f'<div class="generated-post">{st.session_state.post_text}</div>',
            unsafe_allow_html=True,
        )

        # Text copy area
        st.text_area("📋 انسخ النص:", st.session_state.post_text, height=150)

        # Show images if available
        current_image_url = st.session_state.get("image_url")

        if "rss_images" in st.session_state and st.session_state.rss_images:
            st.markdown("### 🖼️ اختر صورة من المصادر:")
            img_cols = st.columns(min(3, len(st.session_state.rss_images)))
            for i, img in enumerate(st.session_state.rss_images[:3]):
                with img_cols[i]:
                    try:
                        st.image(
                            img["url"],
                            caption=img.get("source", ""),
                            use_container_width=True,
                        )
                        if st.button("اختر هذه الصورة", key=f"sel_img_{i}"):
                            current_image_url = img["url"]
                            st.session_state.image_url = current_image_url
                            st.success("تم اختيار الصورة")
                    except:
                        st.warning("تعذر تحميل الصورة")

        if "generated_image" in st.session_state and st.session_state.generated_image:
            # Code removed: AI Generation logic is disabled
            pass

        # --- Facebook Posting Section ---
        st.markdown("---")
        st.markdown("### 🚀 نشر مباشر على فيسبوك")

        col_pub1, col_pub2 = st.columns([1, 2])
        with col_pub1:
            if st.button("📘 انشر الآن", type="primary", use_container_width=True):
                if not fb_token:
                    st.error("❌ يجب إدخال Page Access Token في الإعدادات أو Secrets")
                else:
                    with st.spinner("جاري النشر..."):
                        res, err_msg = post_to_facebook_page(
                            st.session_state.post_text,
                            fb_token,
                            st.session_state.get("image_url"),
                        )
                        if res:
                            st.success(f"✅ تم النشر بنجاح! ID: {res.get('id')}")
                            st.balloons()
                        else:
                            st.error(err_msg)

# ========================================
# TAB 2: Captain Ezz Simulation & Automation
# ========================================
with tab2:
    st.markdown("## 🤖 غرفة عمليات كابتن عز (نظام الأتمتة)")
    st.info("هنا يمكنك التحكم في 'عقل' البوت، وتجربة ما سينشره تلقائياً قبل حدوثه.")

    # --- Configuration Section ---
    with st.expander("⚙️ إعدادات الشخصية والجدولة (تحكم حي)", expanded=False):
        st.info("💡 هذه الإعدادات سترسل إلى سيرفر البوت فوراً.")

        # Webhook URL (Render)
        webhook_url = st.text_input(
            "رابط سيرفر البوت (Render URL)",
            placeholder="https://academy-webhook.onrender.com",
        )

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### ⏰ مواعيد النشر النشطة")
            new_active_hours = st.multiselect(
                "الساعات (بتوقيت مصر)",
                options=list(range(24)),
                default=[9, 11, 14, 17, 20, 22],
                format_func=lambda x: f"{x}:00",
                key="cfg_hours",
            )

        with col2:
            st.markdown("### 🎭 إعدادات الشخصية")
            new_captain_mood = st.select_slider(
                "مود الكابتن",
                options=["رسمي جداً", "متوازن", "حماسي جداً"],
                value="حماسي جداً",
                key="cfg_mood",
            )

        st.markdown("### 📰 مصادر الأخبار (RSS)")
        default_rss = """https://feeds.feedburner.com/karatemart
https://kaizenfitnessusa.com/blog?format=rss
https://karateoc.com/feed
https://www.karatebyjesse.com/feed/
https://kungfu.kids/blog/feed
https://smabloggers.com/tag/kung-fu/feed
https://blackbeltmag.com/feed
https://ymaa.com/publishing/articles/feed
https://sidekickboxing.co.uk/blog/feed/
https://www.ufcgym.com.au/fitness-blog/rss
https://fightcamp.com/blog/rss/
https://shiftmovementscience.com/feed/
https://usagym.org/feed/
https://mountain-kids.com/feed/
https://gymnasticscoaching.com/feed/
https://taekwondonation.com/feed/
https://illinoistkd.com/feed/
http://usnta.net/category/blog/feed/
https://tkdlifemagazine.com/feed/
https://activeforlife.com/feed/
https://changingthegameproject.com/feed/
https://breakingmuscle.com/feed/
https://www.skysewsports.com/rss
https://www.youm7.com/rss/SectionRss?SectionID=298"""

        new_rss_feeds_text = st.text_area(
            "روابط RSS (رابط في كل سطر)", value=default_rss, key="cfg_rss"
        )

        if st.button("💾 حفظ الإعدادات وتحديث البوت", type="primary"):
            if not webhook_url:
                st.error("❌ يرجى إدخال رابط سيرفر Render أولاً!")
            else:
                # Prepare Payload
                feeds_list = [
                    line.strip()
                    for line in new_rss_feeds_text.split("\n")
                    if line.strip()
                ]
                payload = {
                    "active_hours": new_active_hours,
                    "mood": new_captain_mood,
                    "rss_feeds": feeds_list,
                }

                # Send to Webhook
                try:
                    # Clean URL
                    if webhook_url.endswith("/"):
                        webhook_url = webhook_url[:-1]

                    # Assuming secret is hardcoded or user inputs it (Using the hardcoded one for simplicity as per webhook.py)
                    cron_secret = "my_secret_cron_key_123"

                    update_url = f"{webhook_url}/update-config?secret={cron_secret}"

                    with st.spinner("جاري الاتصال بالسيرفر وتحديث العقل..."):
                        resp = requests.post(update_url, json=payload, timeout=10)

                        if resp.status_code == 200:
                            st.success(
                                f"✅ تم تحديث البوت بنجاح! ({resp.json().get('status')})"
                            )
                            st.json(resp.json().get("config"))
                        else:
                            st.error(f"❌ فشل التحديث: {resp.text}")

                except Exception as e:
                    st.error(f"❌ خطأ في الاتصال: {e}")

        # System Status Check
        st.markdown("---")
        st.markdown("### 🚦 حالة النظام")
        col_s1, col_s2 = st.columns([1, 3])
        with col_s1:
            if st.button("🔄 فحص الحالة الحالية"):
                if not webhook_url:
                    st.warning("أدخل رابط السيرفر أولاً")
                else:
                    try:
                        # Clean URL
                        if webhook_url.endswith("/"):
                            webhook_url = webhook_url[:-1]
                            
                        status_res = requests.get(f"{webhook_url}/status", timeout=5)
                        if status_res.status_code == 200:
                            st.session_state.bot_status = status_res.json()
                        else:
                            st.error("السيرفر لا يستجيب بالشكل الصحيح")
                    except Exception as e:
                        st.error(f"فشل الاتصال: {e}")
        
        with col_s2:
            if 'bot_status' in st.session_state:
                bs = st.session_state.bot_status
                st.info(f"""
                - **الحالة:** {bs.get('status')} ✅
                - **توقيت السيرفر:** {bs.get('time_cairo')}
                - **الساعات النشطة:** {bs.get('active_hours')}
                - **عدد المصادر:** {bs.get('rss_count')}
                - **مزاج الكابتن:** {bs.get('mood')}
                - **آخر نشر تلقائي:** {bs.get('last_post_hour')}
                """)

    st.divider()

    # --- Simulation Section ---
    st.markdown("### 🧪 اختبار المحتوى التلقائي")
    st.markdown("اضغط الزر لمحاكاة ما سيفعله البوت **لو كان الوقت الآن هو:**")

    sim_hour = st.slider("اختر ساعة للمحاكاة", 0, 23, 10, format="%d:00")

    if st.button("🔄 محاكاة دورة النشر (Test Run)", type="primary"):
        st.markdown("---")

        # 1. Determine Logic based on time
        post_type = "general"
        if 8 <= sim_hour < 11:
            post_type = "🌞 صباحي (تحفيز)"
        elif 11 <= sim_hour < 14:
            post_type = "🍎 صحة وتغذية"
        elif 14 <= sim_hour < 17:
            post_type = "👶 أطفال ونصائح"
        elif 17 <= sim_hour < 20:
            post_type = "🥋 تمرين وفنيات"
        elif 20 <= sim_hour <= 23:
            post_type = "🌙 عروض وليل"
        else:
            post_type = "😴 وقت النوم (لن يتم نشر شيء)"

        col_res1, col_res2 = st.columns([1, 2])

        with col_res1:
            st.markdown(f"**⏰ الساعة:** `{sim_hour}:00`")
            st.markdown(f"**🎯 نوع المنشور:** `{post_type}`")

            if "النوم" in post_type:
                st.warning("💤 الكابتن نايم دلوقتي. السيستم مش هينشر حاجة.")
            else:
                st.success("✅ السيستم نشط وهينشر.")

        with col_res2:
            if "النوم" not in post_type and groq_key:
                with st.spinner("جاري استدعاء كابتن عز لكتابة المنشور..."):
                    # Simulation Logic
                    default_img = "https://i.ibb.co/xKGpF5sQ/469991854-122136396014386621-3832266993418146234-n.jpg"

                    # Try getting RSS Mock
                    has_rss = random.choice([True, False])
                    rss_data = None
                    if has_rss:
                        rss_data = {
                            "title": "فوائد مذهلة لممارسة الرياضة صباحاً",
                            "link": "http://example.com/sport-news",
                            "image": default_img,
                        }

                    # Generate Prompt
                    sim_prompt = f"اكتب بوست فيسبوك عن {post_type}"
                    if rss_data:
                        sim_prompt += f" مستوحي من خبر بعنوان: {rss_data['title']}"

                    client, model = get_ai_client("Groq", groq_key)
                    if client:
                        mock_response = generate_ai_response(
                            client, model, COACH_SYSTEM_PROMPT, sim_prompt, data
                        )
                        # Save to session state
                        st.session_state.sim_response = mock_response
                        st.session_state.sim_image = default_img
                        st.session_state.sim_generated = True
                    else:
                        st.error("❌ يلزم مفتاح Groq API")

    # Display Simulation Result (Outside the button to persist)
    if st.session_state.get("sim_generated"):
        st.markdown("### 📝 المنشور المتوقع:")
        st.markdown(
            f'<div class="generated-post">{st.session_state.sim_response}</div>',
            unsafe_allow_html=True,
        )

        st.markdown("### 🖼️ الصورة المختارة:")
        st.image(
            st.session_state.sim_image,
            caption="الصورة الافتراضية (أو صورة الخبر)",
            width=300,
        )

        if fb_token:
            if st.button("📢 اعتمد وانشر ده فعلاً", key="force_pub_sim", type="primary"):
                with st.spinner("جاري النشر..."):
                    res, err_msg = post_to_facebook_page(
                        st.session_state.sim_response,
                        fb_token,
                        st.session_state.sim_image,
                    )
                    if res:
                        st.success(f"✅ تم النشر بنجاح! ID: {res.get('id')}")
                        st.balloons()
                    else:
                        st.error(err_msg)

# ========================================
# TAB 3: Chat Bot (Support)
# ========================================
with tab3:
    st.markdown("## 💬 بوت كابتن عز - محاكي الردود")

    data = load_academy_data()
    sports = list(data.get("schedules", {}).keys())

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Quick Reply Buttons
    st.markdown("### 💡 أسئلة سريعة")

    st.markdown("**💰 استفسارات الأسعار:**")
    cols = st.columns(len(sports))
    for i, sport in enumerate(sports):
        with cols[i]:
            if st.button(f"💰 {sport}", key=f"price_{sport}", use_container_width=True):
                st.session_state.chat_messages.append(
                    {"role": "user", "content": f"كام سعر {sport} وإيه المواعيد؟"}
                )
                st.rerun()

    st.markdown("**❓ أسئلة عامة:**")
    general_questions = [
        ("📍 العنوان", "فين مكان الأكاديمية؟"),
        ("🎁 العروض", "في عروض حالياً؟"),
        ("👶 ابني 5 سنين", "ابني عنده 5 سنين، إيه رياضة مناسبة؟"),
        ("📞 التسجيل", "عايز أسجل، أتواصل إزاي؟"),
        ("⭐ تجربة", "في حصة تجربة؟"),
        ("🤔 الفرق", "إيه الفرق بين الكاراتيه والكونغ فو؟"),
    ]

    cols = st.columns(3)
    for i, (label, question) in enumerate(general_questions):
        with cols[i % 3]:
            if st.button(label, key=f"gen_{i}", use_container_width=True):
                st.session_state.chat_messages.append(
                    {"role": "user", "content": question}
                )
                st.rerun()

    st.markdown("---")

    # Chat Display
    for msg in st.session_state.chat_messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="user-bubble">👤 {msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="bot-bubble">🥋 {msg["content"]}</div>',
                unsafe_allow_html=True,
            )

    # Process pending message
    if (
        st.session_state.chat_messages
        and st.session_state.chat_messages[-1]["role"] == "user"
    ):
        if groq_key:
            with st.spinner("🤔 كابتن عز بيفكر..."):
                client, model = get_ai_client("Groq", groq_key)
                if client:
                    response = generate_ai_response(
                        client,
                        model,
                        COACH_SYSTEM_PROMPT,
                        st.session_state.chat_messages[-1]["content"],
                        data,
                    )
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": response}
                    )
                    st.rerun()
        else:
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": "❌ محتاج Groq API Key!"}
            )
            st.rerun()

    # Chat Input
    user_input = st.chat_input("اكتب سؤالك...")
    if user_input:
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        st.rerun()

    # Clear
    if st.button("🗑️ مسح المحادثة"):
        st.session_state.chat_messages = []
        st.rerun()

# ========================================
# TAB 3: Settings
# ========================================
with tab3:
    st.markdown("## ⚙️ الإعدادات")

    data = load_academy_data()

    with st.expander("📋 المعلومات الأساسية", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            academy_name = st.text_input("الاسم", value=data.get("academy_name", ""))
            manager = st.text_input("المدير", value=data.get("manager", ""))
            phone = st.text_input("الهاتف", value=data.get("phone", ""))
            phone_alt = st.text_input("هاتف بديل", value=data.get("phone_alt", ""))
        with col2:
            location = st.text_area(
                "العنوان", value=data.get("location", ""), height=80
            )
            map_link = st.text_input("رابط الخريطة", value=data.get("map_link", ""))
            facebook = st.text_input("فيسبوك", value=data.get("facebook", ""))

    with st.expander("📅 المواعيد"):
        schedules = data.get("schedules", {})
        updated_schedules = {}
        for sport, times in schedules.items():
            times_str = ", ".join(times) if isinstance(times, list) else str(times)
            new_time = st.text_input(f"{sport}", value=times_str, key=f"sched_{sport}")
            updated_schedules[sport] = (
                [t.strip() for t in new_time.split(",")]
                if "," in new_time
                else [new_time]
            )

    with st.expander("💰 الأسعار"):
        pricing = data.get("pricing", {})
        updated_pricing = {}
        for sport, price in pricing.items():
            new_price = st.text_input(f"{sport}", value=price, key=f"price_set_{sport}")
            updated_pricing[sport] = new_price

    with st.expander("🎁 العروض"):
        offers = data.get("offers", [])
        updated_offers = []
        for i, offer in enumerate(offers):
            new_offer = st.text_input(f"عرض {i+1}", value=offer, key=f"offer_{i}")
            if new_offer:
                updated_offers.append(new_offer)
        new_offer_text = st.text_input("➕ عرض جديد", key="new_offer")
        if new_offer_text:
            updated_offers.append(new_offer_text)

    if st.button("💾 حفظ", type="primary", use_container_width=True):
        updated_data = {
            "academy_name": academy_name,
            "manager": manager,
            "location": location,
            "map_link": map_link,
            "facebook": facebook,
            "phone": phone,
            "phone_alt": phone_alt,
            "schedules": updated_schedules or data.get("schedules", {}),
            "pricing": updated_pricing or data.get("pricing", {}),
            "offers": updated_offers or data.get("offers", []),
            "system_prompt": COACH_SYSTEM_PROMPT,
            "content_sources": data.get("content_sources", {}),
        }
        save_academy_data(updated_data)
        st.success("✅ تم الحفظ!")
        st.balloons()

# ========================================
# TAB 4: Overview
# ========================================
with tab4:
    st.markdown("## 📊 نظرة عامة")

    data = load_academy_data()

    st.markdown(
        f"""
    <div class="info-banner">
        <h3 style="margin:0;">🥋 {data.get('academy_name', '')}</h3>
        <p style="margin:0;">📍 {data.get('location', '')}</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

    # Stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🏋️ رياضات", len(data.get("schedules", {})))
    with col2:
        st.metric("🎁 عروض", len(data.get("offers", [])))
    with col3:
        # Get count from session state if available (from status check), else estimate
        rss_count = 30 # Default updated count
        if 'bot_status' in st.session_state:
             rss_count = st.session_state.bot_status.get('rss_count', 30)
             
        st.metric(
            "📰 RSS مصادر",
            f"{rss_count}+"
        )
    with col4:
        st.metric("📝 أنواع محتوى", len(CONTENT_SCENARIOS))

    st.markdown("---")

    # Schedule Table
    st.markdown("### 📅 المواعيد والأسعار")
    table_data = []
    for sport in data.get("schedules", {}):
        table_data.append(
            {
                "الرياضة": sport,
                "المواعيد": ", ".join(data.get("schedules", {}).get(sport, [])),
                "السعر": data.get("pricing", {}).get(sport, "غير محدد"),
            }
        )
    if table_data:
        st.table(table_data)

    # Offers
    st.markdown("### 🎁 العروض")
    for offer in data.get("offers", []):
        st.success(offer)

# ========================================
# TAB 5: System Settings
# ========================================
with tab5:
    st.markdown("## ⚙️ إعدادات النظام الكاملة")
    st.info("💡 هنا يمكنك تخصيص كل جانب من جوانب النظام - الاسم، البيانات، الألوان، كل شيء!")
    
    data = load_academy_data()
    
    # System Branding
    with st.expander("🎨 العلامة التجارية (النظام)", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            system_name = st.text_input(
                "اسم النظام (في الهيدر)",
                value=data.get('system_name', '🥋 مدير أكاديمية أبطال أكتوبر'),
                key="sys_name"
            )
        with col2:
            system_subtitle = st.text_input(
                "نبذة النظام (تحت الهيدر)",
                value=data.get('system_subtitle', 'نظام ذكي لإدارة المحتوى مع توليد الصور 🖼️'),
                key="sys_subtitle"
            )
    
    # Academy Info
    with st.expander("🏢 معلومات الأكاديمية الأساسية", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            academy_name = st.text_input(
                "اسم الأكاديمية",
                value=data.get('academy_name', ''),
                key="set_academy_name"
            )
            manager = st.text_input(
                "اسم المدير",
                value=data.get('manager', ''),
                key="set_manager"
            )
            phone = st.text_input(
                "رقم التواصل الأساسي",
                value=data.get('phone', ''),
                key="set_phone"
            )
            phone_alt = st.text_input(
                "رقم التواصل البديل",
                value=data.get('phone_alt', ''),
                key="set_phone_alt"
            )
        
        with col2:
            location = st.text_area(
                "العنوان",
                value=data.get('location', ''),
                key="set_location",
                height=100
            )
            map_link = st.text_input(
                "رابط الخريطة (Google Maps)",
                value=data.get('map_link', ''),
                key="set_map"
            )
            facebook = st.text_input(
                "رابط الفيسبوك",
                value=data.get('facebook', ''),
                key="set_facebook"
            )
    
    # Schedules & Pricing
    with st.expander("📅 المواعيد والأسعار", expanded=False):
        st.markdown("### إدارة الرياضات")
        
        current_schedules = data.get('schedules', {})
        current_pricing = data.get('pricing', {})
        
        # Add new sport
        col_new1, col_new2, col_new3 = st.columns([2, 2, 1])
        with col_new1:
            new_sport_name = st.text_input("اسم رياضة جديدة", key="new_sport_input")
        with col_new2:
            new_sport_schedule = st.text_input("الموعد", placeholder="مثال: الأحد والثلاثاء - 4:30 م", key="new_sport_schedule")
        with col_new3:
            new_sport_price = st.text_input("السعر", placeholder="500 جنيه", key="new_sport_price")
        
        if st.button("➕ إضافة رياضة", key="add_sport_btn"):
            if new_sport_name and new_sport_schedule and new_sport_price:
                current_schedules[new_sport_name] = [new_sport_schedule]
                current_pricing[new_sport_name] = new_sport_price
                st.success(f"تمت إضافة {new_sport_name}!")
                st.rerun()
        
        st.markdown("---")
        st.markdown("### تعديل الرياضات الحالية")
        
        updated_schedules = {}
        updated_pricing = {}
        
        for sport in list(current_schedules.keys()):
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                schedule_text = st.text_input(
                    f"موعد {sport}",
                    value=", ".join(current_schedules.get(sport, [])),
                    key=f"schedule_{sport}"
                )
                if schedule_text:
                    updated_schedules[sport] = [schedule_text]
            
            with col2:
                price_text = st.text_input(
                    f"سعر {sport}",
                    value=current_pricing.get(sport, ''),
                    key=f"price_{sport}"
                )
                if price_text:
                    updated_pricing[sport] = price_text
            
            with col3:
                if st.button("🗑️", key=f"del_{sport}"):
                    current_schedules.pop(sport, None)
                    current_pricing.pop(sport, None)
                    st.rerun()
    
    # Offers
    with st.expander("🎁 العروض الحالية", expanded=False):
        current_offers = data.get('offers', [])
        updated_offers = []
        
        for i, offer in enumerate(current_offers):
            col1, col2 = st.columns([5, 1])
            with col1:
                edited_offer = st.text_area(
                    f"عرض {i+1}",
                    value=offer,
                    key=f"offer_edit_{i}",
                    height=60
                )
                if edited_offer:
                    updated_offers.append(edited_offer)
            with col2:
                if st.button("🗑️", key=f"del_offer_{i}"):
                    pass  # Skip this offer
                else:
                    pass  # Keep it (already added above)
        
        new_offer = st.text_area("➕ عرض جديد", key="new_offer_input", height=60)
        if new_offer:
            updated_offers.append(new_offer)
    
    # Save Button
    st.markdown("---")
    if st.button("� حفظ كل الإعدادات", type="primary", use_container_width=True):
        # Merge all updates
        final_schedules = {**current_schedules, **updated_schedules}
        final_pricing = {**current_pricing, **updated_pricing}
        
        complete_data = {
            "system_name": system_name,
            "system_subtitle": system_subtitle,
            "academy_name": academy_name,
            "manager": manager,
            "phone": phone,
            "phone_alt": phone_alt,
            "location": location,
            "map_link": map_link,
            "facebook": facebook,
            "schedules": final_schedules,
            "pricing": final_pricing,
            "offers": updated_offers if updated_offers else current_offers,
            "system_prompt": data.get('system_prompt', COACH_SYSTEM_PROMPT),
            "content_sources": data.get('content_sources', {})
        }
        
        save_academy_data(complete_data)
        st.success("✅ تم حفظ جميع الإعدادات بنجاح!")
        st.balloons()
        time.sleep(1)
        st.rerun()

# ========================================
# TAB 5: System Settings
# ========================================
with tab5:
    st.markdown("## ⚙️ إعدادات النظام الكاملة")
    st.info("💡 هنا يمكنك تخصيص كل جانب من جوانب النظام - الاسم، البيانات، كل شيء!")
    
    data = load_academy_data()
    
    # System Branding
    with st.expander("🎨 العلامة التجارية (النظام)", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            system_name = st.text_input(
                "اسم النظام (في الهيدر)",
                value=data.get('system_name', '🥋 مدير أكاديمية أبطال أكتوبر'),
                key="sys_name"
            )
        with col2:
            system_subtitle = st.text_input(
                "نبذة النظام (تحت الهيدر)",
                value=data.get('system_subtitle', 'نظام ذكي لإدارة المحتوى مع توليد الصور 🖼️'),
                key="sys_subtitle"
            )
    
    # Academy Info
    with st.expander("🏢 معلومات الأكاديمية الأساسية", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            academy_name = st.text_input(
                "اسم الأكاديمية",
                value=data.get('academy_name', ''),
                key="set_academy_name"
            )
            manager = st.text_input(
                "اسم المدير",
                value=data.get('manager', ''),
                key="set_manager"
            )
            phone = st.text_input(
                "رقم التواصل الأساسي",
                value=data.get('phone', ''),
                key="set_phone"
            )
            phone_alt = st.text_input(
                "رقم التواصل البديل",
                value=data.get('phone_alt', ''),
                key="set_phone_alt"
            )
        
        with col2:
            location = st.text_area(
                "العنوان",
                value=data.get('location', ''),
                key="set_location",
                height=100
            )
            map_link = st.text_input(
                "رابط الخريطة (Google Maps)",
                value=data.get('map_link', ''),
                key="set_map"
            )
            facebook = st.text_input(
                "رابط الفيسبوك",
                value=data.get('facebook', ''),
                key="set_facebook"
            )
    
    # Schedules & Pricing
    with st.expander("📅 المواعيد والأسعار", expanded=False):
        st.markdown("### إدارة الرياضات")
        
        current_schedules = data.get('schedules', {})
        current_pricing = data.get('pricing', {})
        
        # Add new sport
        col_new1, col_new2, col_new3 = st.columns([2, 2, 1])
        with col_new1:
            new_sport_name = st.text_input("اسم رياضة جديدة", key="new_sport_input")
        with col_new2:
            new_sport_schedule = st.text_input("الموعد", placeholder="مثال: الأحد والثلاثاء - 4:30 م", key="new_sport_schedule")
        with col_new3:
            new_sport_price = st.text_input("السعر", placeholder="500 جنيه", key="new_sport_price")
        
        if st.button("➕ إضافة رياضة", key="add_sport_btn"):
            if new_sport_name and new_sport_schedule and new_sport_price:
                current_schedules[new_sport_name] = [new_sport_schedule]
                current_pricing[new_sport_name] = new_sport_price
                st.success(f"تمت إضافة {new_sport_name}!")
                st.rerun()
        
        st.markdown("---")
        st.markdown("### تعديل الرياضات الحالية")
        
        updated_schedules = {}
        updated_pricing = {}
        
        for sport in list(current_schedules.keys()):
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                schedule_text = st.text_input(
                    f"موعد {sport}",
                    value=", ".join(current_schedules.get(sport, [])),
                    key=f"schedule_{sport}"
                )
                if schedule_text:
                    updated_schedules[sport] = [schedule_text]
            
            with col2:
                price_text = st.text_input(
                    f"سعر {sport}",
                    value=current_pricing.get(sport, ''),
                    key=f"price_{sport}"
                )
                if price_text:
                    updated_pricing[sport] = price_text
            
            with col3:
                if st.button("�️", key=f"del_{sport}"):
                    current_schedules.pop(sport, None)
                    current_pricing.pop(sport, None)
                    st.rerun()
    
    # Offers
    with st.expander("🎁 العروض الحالية", expanded=False):
        current_offers = data.get('offers', [])
        updated_offers = []
        
        for i, offer in enumerate(current_offers):
            col1, col2 = st.columns([5, 1])
            with col1:
                edited_offer = st.text_area(
                    f"عرض {i+1}",
                    value=offer,
                    key=f"offer_edit_{i}",
                    height=60
                )
                if edited_offer:
                    updated_offers.append(edited_offer)
            with col2:
                if st.button("🗑️", key=f"del_offer_{i}"):
                    pass  # Skip this offer
        
        new_offer = st.text_area("➕ عرض جديد", key="new_offer_input", height=60)
        if new_offer:
            updated_offers.append(new_offer)
    
    # Subscription Management
    with st.expander("💳 إدارة الاشتراكات والأكواد (SaaS)", expanded=False):
        st.markdown("### 🎟️ توليد أكواد الاشتراك")
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            voucher_count = st.number_input("عدد الأكواد", min_value=1, max_value=1000, value=20, key="voucher_count")
        with col2:
            voucher_days = st.number_input("مدة الاشتراك (يوم)", min_value=1, max_value=365, value=30, key="voucher_days")
        with col3:
            st.markdown("**الكود السري:**")
            st.info("بلح ← طرح ← موز")
        
        st.markdown("**أدخل كود المدير (3 خطوات):**")
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            step1 = st.text_input("الخطوة الأولى", placeholder="بلح", key="admin_step1")
        with col_s2:
            step2 = st.text_input("الخطوة الثانية", placeholder="طرح", key="admin_step2")  
        with col_s3:
            step3 = st.text_input("الخطوة الثالثة", placeholder="موز", key="admin_step3")
        
        if st.button("🎫 توليد الأكواد", type="primary", key="gen_vouchers_btn"):
            if not step1 or not step2 or not step3:
                st.error("يجب إدخال الخطوات الثلاث للكود السري!")
            else:
                try:
                    import requests
                    response = requests.post(
                        "http://localhost:5000/gen-vouchers",
                        json={
                            "step1": step1,
                            "step2": step2, 
                            "step3": step3,
                            "count": voucher_count,
                            "duration_days": voucher_days
                        },
                        timeout=10
                    )
                    if response.status_code == 200:
                        result = response.json()
                        st.success(f"✅ تم توليد {result['count']} كود لمدة {result['duration_days']} يوم")
                        
                        # Display codes in a downloadable format
                        codes_text = "\n".join(result["codes"])
                        st.download_button(
                            "📥 تحميل الأكواد",
                            data=codes_text,
                            file_name=f"vouchers_{voucher_count}_{voucher_days}days.txt",
                            mime="text/plain"
                        )
                        
                        # Display codes
                        with st.expander("👀 عرض الأكواد", expanded=False):
                            st.code(codes_text, language="text")
                    else:
                        error_data = response.json() if response.content else {"message": response.text}
                        st.error(f"❌ {error_data.get('message', 'خطأ في التوليد')}")
                except Exception as e:
                    st.error(f"❌ خطأ في الاتصال: {str(e)}")
        
        st.markdown("---")
        st.markdown("### 🔑 تفعيل اشتراك")
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            activate_user_id = st.text_input("معرف المستخدم", key="activate_user_id")
        with col2:
            activate_code = st.text_input("كود الاشتراك", key="activate_code")
        with col3:
            if st.button("✅ تفعيل", key="activate_btn"):
                if not activate_user_id or not activate_code:
                    st.error("معرف المستخدم وكود الاشتراك مطلوبان!")
                else:
                    try:
                        import requests
                        response = requests.post(
                            "http://localhost:5000/activate",
                            json={"user_id": activate_user_id, "code": activate_code},
                            timeout=10
                        )
                        if response.status_code == 200:
                            result = response.json()
                            if result["status"] == "activated":
                                st.success(f"✅ تم تفعيل الاشتراك حتى: {result['subscription_end']}")
                            else:
                                st.error(f"❌ {result.get('message', 'خطأ في التفعيل')}")
                        else:
                            error_data = response.json() if response.content else {"message": response.text}
                            st.error(f"❌ {error_data.get('message', 'خطأ في التفعيل')}")
                    except Exception as e:
                        st.error(f"❌ خطأ في الاتصال: {str(e)}")
        
        st.markdown("---")
        st.markdown("### 📊 فحص حالة الاشتراك")
        col1, col2 = st.columns([3, 1])
        with col1:
            check_user_id = st.text_input("معرف المستخدم للفحص", key="check_user_id")
        with col2:
            if st.button("🔍 فحص", key="check_status_btn"):
                if not check_user_id:
                    st.error("معرف المستخدم مطلوب!")
                else:
                    try:
                        import requests
                        response = requests.get(
                            f"http://localhost:5000/subscription-status?user_id={check_user_id}",
                            timeout=10
                        )
                        if response.status_code == 200:
                            result = response.json()
                            if result["active"]:
                                st.success(f"✅ الاشتراك نشط حتى: {result.get('subscription_end', 'غير محدد')}")
                            else:
                                st.warning("⚠️ الاشتراك غير نشط أو منتهي الصلاحية")
                        else:
                            st.error(f"❌ خطأ في الفحص: {response.text}")
                    except Exception as e:
                        st.error(f"❌ خطأ في الاتصال: {str(e)}")
    
    # Save Button
    st.markdown("---")
    if st.button("💾 حفظ كل الإعدادات", type="primary", use_container_width=True):
        # Merge all updates
        final_schedules = {**current_schedules, **updated_schedules}
        final_pricing = {**current_pricing, **updated_pricing}
        
        complete_data = {
            "system_name": system_name,
            "system_subtitle": system_subtitle,
            "academy_name": academy_name,
            "manager": manager,
            "phone": phone,
            "phone_alt": phone_alt,
            "location": location,
            "map_link": map_link,
            "facebook": facebook,
            "schedules": final_schedules,
            "pricing": final_pricing,
            "offers": updated_offers if updated_offers else current_offers,
            "system_prompt": data.get('system_prompt', COACH_SYSTEM_PROMPT),
            "content_sources": data.get('content_sources', {})
        }
        
        save_academy_data(complete_data)
        st.success("✅ تم حفظ جميع الإعدادات بنجاح!")
        st.balloons()
        time.sleep(1)
        st.rerun()

# --- Footer ---
st.markdown("---")
footer_data = load_academy_data()
st.markdown(
    f"""
<div style="text-align: center; color: #888; padding: 1rem;">
    🥋 <strong>{footer_data.get('academy_name', 'الأكاديمية')}</strong> - v4.0 Multi-Tenant Ready<br>
    <small>Powered by Groq + Facebook API 🚀</small>
</div>
""",
    unsafe_allow_html=True,
)
