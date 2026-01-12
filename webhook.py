from flask import Flask, request, jsonify
import os
from groq import Groq
import requests

app = Flask(__name__)

# API Keys from environment
GROQ_API_KEY = os.environ.get("GROQ_API_KEY_4")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = "academy_webhook_2026"

# Initialize Groq
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

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

SYSTEM_PROMPT = """أنت "كابتن عز غريب" - مدير ومدرب أكاديمية أبطال أكتوبر للفنون القتالية والجمباز.

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
