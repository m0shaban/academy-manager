from flask import Flask, request, jsonify
import os
from groq import Groq
import requests
import feedparser
from bs4 import BeautifulSoup
import random
from datetime import datetime
import pytz

app = Flask(__name__)

# API Keys from environment
GROQ_API_KEY = os.environ.get("GROQ_API_KEY_4")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = "academy_webhook_2026"
CRON_SECRET = "my_secret_cron_key_123" # حماية للرابط عشان محدش غيرك يشغله

# Initialize Groq
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# RSS Feeds for Sports & Health Content
RSS_FEEDS = [
    "https://www.skysewsports.com/rss",  # General Sports
    "https://feeds.feedburner.com/AceFitFacts", # Fitness Facts
    # يمكن إضافة المزيد لاحقاً
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
        "تايكوندو": ["بالاتفاق مع الكابتن"]
    },
    "pricing": {
        "كاراتيه": "500 جنيه/شهر",
        "كونغ فو": "500 جنيه/شهر",
        "كيك بوكسينج": "500 جنيه/شهر",
        "جمباز": "600 جنيه/شهر",
        "تايكوندو": "600 جنيه/شهر",
        "ملاكمة": "600 جنيه/شهر"
    },
    "offers": [
        "🎉 بمناسبة العام الجديد - بادر بالحجز لفترة محدودة!",
        "💪 اشتراك شهري للكاراتيه والكونغ فو والكيك بوكس 500 جنيه فقط!",
        "🤸 الجمباز والتايكوندو والملاكمة 600 جنيه لفترة محدودة!"
    ]
}

SYSTEM_PROMPT = """أنت "كابتن عز غريب"، صانع محتوى رياضي ومدرب خبير، ومدير "أكاديمية أبطال أكتوبر".

شخصيتك وأسلوبك:
1.  **صانع محتوى حقيقي:** لا تتحدث كأنك روبوت خدمة عملاء. تكلم كأنك "إنفلونسر" رياضي فاهم ومجرب.
2.  **اللغة:** عامية مصرية راقية ومحفزة (يا بطل، يا وحش، عاش، استمر).
3.  **الهدف:** تقديم قيمة حقيقية (نصائح، تحفيز، معلومات) وبناء ثقة، ثم التسويق للأكاديمية بشكل ذكي وغير مباشر أحياناً، ومباشر أحياناً أخرى.
4.  **المحتوى:**
    *   نصائح تغذية وتمرين حقيقية وعلمية.
    *   تجارب عملية من الصالة (التمرين بيعلم الصبر، شفت النهاردة ولد صغير بيعمل...).
    *   تحفيز قوي للالتزام.
    *   معلومات عن رياضات الأكاديمية (الجمباز بيقوي الأعصاب، الكاراتيه مش بس ضرب...).

لا تستخدم جمل تقليدية مثل "يسعدنا انضمامك". قل بدلاً منها: "مستني إيه؟ مكانك موجود في فريق الأبطال!".
"""

def get_cairo_time():
    """Get current time in Cairo"""
    cairo_tz = pytz.timezone('Africa/Cairo')
    return datetime.now(cairo_tz)

def extract_image_from_url(url):
    """Attempt to extract the main image from a webpage/article"""
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
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
        post_type = "motivation_morning" # صباح وتفاؤل
    elif 11 <= current_hour < 14:
        post_type = "health_tip" # نصيحة في وسط اليوم
    elif 14 <= current_hour < 17:
        post_type = "kids_advice" # نصيحة للأمهات والأطفال بعد المدرسة
    elif 17 <= current_hour < 20:
        post_type = "training_drill" # وقت التمرين
    elif 20 <= current_hour <= 23:
        post_type = "academy_offer" # عرض مباشر للحجز
    
    # تفضيل احضار محتوى خارجي للتعليق عليه (Curated Content)
    try:
        if random.choice([True, False]): # 50% فرصة لجلب محتوى خارجي
            feed = feedparser.parse(random.choice(RSS_FEEDS))
            if feed.entries:
                entry = random.choice(feed.entries[:5])
                image_url = extract_image_from_url(entry.link)
                return {
                    "type": "curated",
                    "title": entry.title,
                    "link": entry.link,
                    "summary": entry.get('summary', ''),
                    "image_url": image_url
                }
    except:
        pass
        
    # لو فشل ال RSS، ارجع لإنشاء محتوى أصلي
    return {"type": "original", "category": post_type, "image_url": None}

def generate_social_post(idea):
    """Generate the post text using Groq"""
    
    if idea['type'] == 'curated':
        prompt = f"""
        أنت كابتن عز غريب. لقيت المقال ده عن الرياضة:
        العنوان: {idea['title']}
        الملخص: {idea['summary']}
        
        اكتب بوست فيسبوك تعلق فيه على الموضوع ده من وجهة نظرك كمدرب.
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
            "academy_offer": "بوست دعائي مباشر بس بأسلوب 'خايف على مصلحتك'.. الحق مكانك في عروض السنة الجديدة."
        }
        topic_desc = topics.get(idea['category'], "نصيحة رياضية عامة")
        
        prompt = f"""
        أنت كابتن عز غريب.
        اكتب بوست فيسبوك عن: {topic_desc}
        
        الأسلوب:
        - عامية مصرية، فيها روح وتشجيع.
        - استخدم إيموجي مناسبة 🥊🥋💪.
        - خلي الكلام مقسم فقرات قصيرة (سهل القراءة).
        - اختم بـ Call to Action (سؤال للمتابعين، أو دعوة للتمرين).
        """
        
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + f"\nبيانات الأكاديمية: {ACADEMY_DATA}"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.8
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
    
    for sport, times in ACADEMY_DATA['schedules'].items():
        context += f"\n- {sport}: {', '.join(times)}"
    
    context += "\n\n💰 الأسعار:\n"
    for sport, price in ACADEMY_DATA['pricing'].items():
        context += f"- {sport}: {price}\n"
    
    context += "\n🎁 العروض الحالية:\n"
    for offer in ACADEMY_DATA['offers']:
        context += f"- {offer}\n"
    
    full_system_prompt = f"{SYSTEM_PROMPT}\n\n{context}"
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=800,
            temperature=0.7
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
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    
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

@app.route('/')
def home():
    """Health check endpoint"""
    return jsonify({
        "status": "running",
        "service": "Academy Manager Webhook",
        "version": "1.0"
    })

@app.route('/auto-post-trigger', methods=['GET', 'POST'])
def auto_scheduler():
    """
    هذا الرابط يتم استدعاؤه بواسطة خدمة Cron Job خارجية
    للنشر التلقائي في المواعيد المحددة
    """
    # 1. Security Check
    secret = request.args.get('secret')
    if secret != CRON_SECRET:
        return "Unauthorized", 401
    
    # 2. Time Check (Cairo 8 AM - 12 AM)
    cairo_now = get_cairo_time()
    if not (8 <= cairo_now.hour <= 23):
        return f"Sleeping time in Cairo (Hour: {cairo_now.hour}). No posts.", 200
        
    # 3. Generate Content
    idea = fetch_content_idea()
    post_text = generate_social_post(idea)
    
    if post_text:
        # 4. Publish
        result = publish_to_facebook(post_text, idea.get('image_url'))
        return jsonify({
            "status": "success",
            "time": str(cairo_now),
            "type": idea.get('type'),
            "result": result
        })
    
    return "Failed to generate content", 500

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Webhook verification for Facebook"""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        print("✅ Webhook verified successfully!")
        return challenge, 200
    else:
        print("❌ Webhook verification failed")
        return 'Forbidden', 403

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handle incoming Facebook webhooks"""
    data = request.get_json()
    
    print(f"📨 Received webhook: {data}")
    
    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            # Handle Messenger Messages
            for messaging in entry.get('messaging', []):
                sender_id = messaging['sender']['id']
                
                if 'message' in messaging and 'text' in messaging['message']:
                    message_text = messaging['message']['text']
                    print(f"💬 Message from {sender_id}: {message_text}")
                    
                    # Generate response
                    response = generate_response(message_text)
                    
                    # Send back
                    send_message(sender_id, response)
            
            # Handle Comments
            for change in entry.get('changes', []):
                if change.get('field') == 'feed':
                    value = change.get('value', {})
                    
                    if value.get('item') == 'comment':
                        comment_id = value.get('comment_id')
                        message = value.get('message', '')
                        
                        print(f"💭 Comment {comment_id}: {message}")
                        
                        # Generate response
                        response = generate_response(message)
                        
                        # Reply to comment
                        reply_to_comment(comment_id, response)
    
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
