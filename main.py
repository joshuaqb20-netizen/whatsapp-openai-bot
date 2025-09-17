from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import os

app = Flask(__name__)

# ✅ Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ✅ Root route just for testing in Webview
@app.route("/", methods=["GET"])
def home():
    return "🚀 Flask server is running!"

# ✅ WhatsApp webhook route
@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    # Incoming WhatsApp message
    incoming_msg = request.values.get("Body", "").strip()
    print(f"📩 Incoming WhatsApp message: {incoming_msg}")

    # Default reply if OpenAI fails
    reply_text = "Sorry, something went wrong. Please try again."

    try:
        # Call OpenAI
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful AI chatbot."},
                {"role": "user", "content": incoming_msg},
            ],
        )

        reply_text = response.choices[0].message.content
        print(f"🤖 OpenAI reply: {reply_text}")

    except Exception as e:
        print(f"⚠️ Error with OpenAI API: {e}")

    # Send reply back to WhatsApp via Twilio
    twilio_resp = MessagingResponse()
    twilio_resp.message(reply_text)
    return str(twilio_resp)

if __name__ == "__main__":
    # ✅ Important: Replit requires port 8000
    app.run(host="0.0.0.0", port=8000, debug=True)
