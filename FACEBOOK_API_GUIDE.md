# Facebook Graph API Integration Guide

This guide explains how to connect the Smart Academy Manager to real Facebook Messenger and Comments.

## Prerequisites

1. **Facebook Developer Account**: [developers.facebook.com](https://developers.facebook.com)
2. **Facebook Page** for your academy
3. **SSL Certificate** for webhook endpoint (HTTPS required)
4. **Public Server** (or ngrok for testing)

---

## Step 1: Create Facebook App

1. Go to [Facebook Developers](https://developers.facebook.com/apps/)
2. Click **Create App** → Choose **Business** type
3. Enter app name: "Smart Academy Bot"
4. Add these products:
   - **Messenger** (for DMs)
   - **Webhooks** (for Comments)

---

## Step 2: Configure Messenger

### Get Page Access Token

1. Go to **Messenger** → **Settings**
2. Under **Access Tokens**, click **Add or Remove Pages**
3. Select your academy's Facebook Page
4. Click **Generate Token** and save it securely

### Subscribe to Events

Subscribe to these webhook events:

- `messages` - Incoming DMs
- `messaging_postbacks` - Button clicks
- `feed` - Page posts and comments

---

## Step 3: Set Up Webhooks

### Webhook Endpoint (Flask Example)

Create `webhook_server.py`:

```python
from flask import Flask, request, jsonify
import json
import requests
from app import load_academy_data, generate_ai_response, get_ai_client

app = Flask(__name__)

# Configuration
PAGE_ACCESS_TOKEN = "YOUR_PAGE_ACCESS_TOKEN"
VERIFY_TOKEN = "YOUR_VERIFY_TOKEN"
API_KEY = "YOUR_GROQ_OR_OPENAI_KEY"
API_PROVIDER = "Groq"  # or "OpenAI"

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """Facebook webhook verification."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        return challenge, 200
    return 'Forbidden', 403

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Handle incoming messages and comments."""
    data = request.get_json()
    
    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            # Handle Messages
            for messaging in entry.get('messaging', []):
                sender_id = messaging['sender']['id']
                if 'message' in messaging:
                    text = messaging['message'].get('text', '')
                    response = generate_bot_response(text)
                    send_message(sender_id, response)
            
            # Handle Comments
            for change in entry.get('changes', []):
                if change.get('field') == 'feed':
                    value = change.get('value', {})
                    if value.get('item') == 'comment':
                        comment_id = value.get('comment_id')
                        message = value.get('message', '')
                        response = generate_bot_response(message)
                        reply_to_comment(comment_id, response)
    
    return 'OK', 200

def generate_bot_response(user_message):
    """Generate AI response using academy data."""
    data = load_academy_data()
    client, model = get_ai_client(API_PROVIDER, API_KEY)
    
    if client:
        return generate_ai_response(
            client, model,
            data.get('system_prompt', ''),
            user_message,
            data
        )
    return "عذراً، حدث خطأ. يرجى التواصل معنا مباشرة."

def send_message(recipient_id, message_text):
    """Send message via Messenger API."""
    url = f"https://graph.facebook.com/v18.0/me/messages"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    requests.post(url, params=params, json=data)

def reply_to_comment(comment_id, message):
    """Reply to a comment."""
    url = f"https://graph.facebook.com/v18.0/{comment_id}/comments"
    params = {"access_token": PAGE_ACCESS_TOKEN}
    data = {"message": message}
    requests.post(url, params=params, json=data)

if __name__ == '__main__':
    app.run(port=5000, debug=True)
```

### Expose Locally with ngrok (Testing)

```bash
ngrok http 5000
```

Use the HTTPS URL (e.g., `https://abc123.ngrok.io/webhook`) as your webhook URL.

---

## Step 4: Configure Webhook in Facebook

1. Go to **Webhooks** in your app settings
2. Click **Edit Subscription**
3. Enter:
   - **Callback URL**: `https://your-server.com/webhook`
   - **Verify Token**: Your `VERIFY_TOKEN`
4. Subscribe to: `messages`, `feed`, `messaging_postbacks`

---

## Step 5: Required Permissions

Request these permissions in **App Review**:

- `pages_messaging` - Send/receive messages
- `pages_read_engagement` - Read comments
- `pages_manage_engagement` - Reply to comments
- `pages_read_user_content` - Read user posts

---

## Step 6: Production Deployment

### Recommended Stack

1. **Server**: AWS EC2 / Google Cloud / DigitalOcean
2. **SSL**: Let's Encrypt (free)
3. **Process Manager**: PM2 or Supervisor
4. **Reverse Proxy**: Nginx

### Environment Variables

```bash
export PAGE_ACCESS_TOKEN="your_token"
export VERIFY_TOKEN="your_verify_token"
export GROQ_API_KEY="your_groq_key"
```

### Nginx Configuration

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    location /webhook {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Security Best Practices

1. **Validate Webhook Signature**: Verify `X-Hub-Signature-256` header
2. **Rate Limiting**: Implement request throttling
3. **Error Handling**: Log errors, don't expose stack traces
4. **Token Security**: Never commit tokens to git

### Signature Validation Example

```python
import hmac
import hashlib

def verify_signature(payload, signature, app_secret):
    expected = hmac.new(
        app_secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

---

## Quick Reference

| Feature | Endpoint | Method |
|---------|----------|--------|
| Send Message | `/me/messages` | POST |
| Reply to Comment | `/{comment-id}/comments` | POST |
| Get Page Posts | `/{page-id}/feed` | GET |
| Webhook Verify | `/webhook` | GET |
| Webhook Events | `/webhook` | POST |

---

## Resources

- [Messenger Platform Docs](https://developers.facebook.com/docs/messenger-platform)
- [Webhooks Reference](https://developers.facebook.com/docs/graph-api/webhooks)
- [Graph API Explorer](https://developers.facebook.com/tools/explorer)
