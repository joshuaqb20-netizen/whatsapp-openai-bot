from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from openai import OpenAI
import os
import requests

# === Database imports ===
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# === Database setup ===
engine = create_engine("sqlite:///chat_history.db")
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)   # WhatsApp number
    role = Column(String)                  # "user" or "assistant"
    content = Column(Text)                 # message text

Base.metadata.create_all(bind=engine)

# === Flask app setup ===
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Twilio setup
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
if not twilio_number:
    raise ValueError("TWILIO_PHONE_NUMBER environment variable is not set")
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

# Unsplash API key
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
if not UNSPLASH_ACCESS_KEY:
    raise ValueError("UNSPLASH_ACCESS_KEY environment variable is not set")

def fetch_image_url(query: str) -> str | None:
    """Search Unsplash for a query and return the first image URL"""
    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": query,
        "per_page": 1,
        "client_id": UNSPLASH_ACCESS_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()
    if data.get("results"):
        return data["results"][0]["urls"]["regular"]
    return None

# ✅ Root route for testing
@app.route("/", methods=["GET"])
def home():
    return "🚀 Flask server is running with memory and image search!"

# ✅ WhatsApp webhook route
@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    db = SessionLocal()
    from_number = request.values.get("From", "")
    incoming_msg = request.values.get("Body", "").strip()
    print(f"📩 Incoming WhatsApp message from {from_number}: {incoming_msg}")

    # === Reset history if user types "reset" ===
    if incoming_msg.lower() == "reset":
        db.query(Message).filter_by(user_id=from_number).delete()
        db.commit()
        reply_text = "🗑️ Chat history reset. Let's start fresh!"
        twilio_resp = MessagingResponse()
        twilio_resp.message(reply_text)
        return str(twilio_resp)

    # === Detect image request ===
    if incoming_msg.lower().startswith("image:") or incoming_msg.lower().startswith("show me"):
        keyword = incoming_msg.lower().replace("image:", "").replace("show me", "").strip()
        media_url = fetch_image_url(keyword)
        if media_url:
            reply_text = f"🖼 Here’s an image of '{keyword}':"
            # Send the image via Twilio
            twilio_client.messages.create(
                from_="whatsapp:" + twilio_number,
                to=from_number,
                body=reply_text,
                media_url=[media_url]
            )
        else:
            reply_text = f"Sorry, I couldn't find an image for '{keyword}'."
            twilio_resp = MessagingResponse()
            twilio_resp.message(reply_text)
            return str(twilio_resp)

        # Save user command and bot reply to DB
        db.add(Message(user_id=from_number, role="user", content=incoming_msg))
        db.add(Message(user_id=from_number, role="assistant", content=reply_text))
        db.commit()
        return ""  # Twilio handled response separately

    # === Normal chat message ===
    db.add(Message(user_id=from_number, role="user", content=incoming_msg))
    db.commit()

    # Load last 10 messages for context
    history = (
        db.query(Message)
        .filter_by(user_id=from_number)
        .order_by(Message.id.desc())
        .limit(10)
        .all()
    )
    history = list(reversed(history))  # oldest first

    # Use dictionaries for messages, ignore Pyright type error
    messages = [{"role": str(msg.role), "content": str(msg.content)} for msg in history]

    # Default reply in case OpenAI fails
    reply_text = "Sorry, something went wrong. Please try again."

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are a helpful AI chatbot."}] + messages,  # type: ignore
        )
        reply_text = response.choices[0].message.content
        print(f"🤖 OpenAI reply: {reply_text}")

        # Save bot reply
        db.add(Message(user_id=from_number, role="assistant", content=reply_text))
        db.commit()
    except Exception as e:
        print(f"⚠️ Error with OpenAI API: {e}")

    # Send reply back to WhatsApp
    twilio_resp = MessagingResponse()
    twilio_resp.message(reply_text)
    return str(twilio_resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
