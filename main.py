from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import os

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

# ✅ Root route just for testing
@app.route("/", methods=["GET"])
def home():
    return "🚀 Flask server is running with memory!"

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
    else:
        # Save user message
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

        messages = [{"role": msg.role, "content": msg.content} for msg in history]

        # Default reply in case OpenAI fails
        reply_text = "Sorry, something went wrong. Please try again."

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "You are a helpful AI chatbot."}] + messages,
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
