"""
chatbot.py
----------
Twilio WhatsApp chatbot using the sandbox.

Setup:
  1. Go to console.twilio.com → Messaging → Try it out → Send a WhatsApp message
  2. WhatsApp the sandbox number with the join code (e.g. "join yellow-tiger")
  3. In Sandbox Settings, set webhook URL to: https://your-ngrok-url/sms
  4. Run ngrok: ngrok http 8080
  5. Run this: python3 chatbot.py

Requirements:
  pip install flask twilio
"""

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os

app = Flask(__name__)

# ── Twilio credentials ─────────────────────────────────────────────────────────
# Get these from console.twilio.com → Dashboard (top of the page)
TWILIO_ACCOUNT_SID     = "PASTE_YOUR_ACCOUNT_SID_HERE"   # starts with AC
TWILIO_AUTH_TOKEN      = "PASTE_YOUR_AUTH_TOKEN_HERE"
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"          # always this for sandbox

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# ── Business logic ─────────────────────────────────────────────────────────────
def process_message(sender: str, message: str) -> str:
    """
    Read the incoming message and return a reply string.
    sender looks like: "whatsapp:+15718881874"
    Plug in real Nessie calls wherever you see # TODO
    """
    msg = message.lower().strip()

    if msg == "help":
        return (
            "💳 *FinanceBot Commands*\n\n"
            "• *BALANCE* — check your balance\n"
            "• *SPENDING* — this month's summary\n"
            "• *TRANSACTIONS* — recent activity\n"
            "• *HELP* — show this menu"
        )

    elif msg == "balance":
        # TODO: replace with real Nessie call
        return "💵 Your current balance is *$1,240.50* (demo)"

    elif msg == "spending":
        # TODO: replace with real Nessie call
        return "📊 This month: *$842.10* across *23* transactions (demo)"

    elif msg == "transactions":
        # TODO: replace with real Nessie call
        return (
            "📋 Recent transactions (demo):\n"
            "• $12.50 — Starbucks\n"
            "• $52.40 — Target\n"
            "• $8.99 — Netflix\n"
            "• $34.20 — Whole Foods\n"
            "• $24.75 — Uber"
        )

    else:
        # Anything not matched — echo it back
        return f"Echo: {message}\n\nText *HELP* to see available commands."


# ── Incoming WhatsApp webhook ──────────────────────────────────────────────────
@app.route("/sms", methods=["POST"])
def incoming_message():
    sender       = request.form.get("From", "")    # e.g. "whatsapp:+15718881874"
    user_message = request.form.get("Body", "").strip()

    print(f"📱 [{sender}]: {user_message}")

    reply = process_message(sender, user_message)

    print(f"📤 Replying: {reply}")

    resp = MessagingResponse()
    resp.message(reply)
    return str(resp), 200, {"Content-Type": "text/xml"}


# ── Health check ───────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return "✅ WhatsApp chatbot is running!", 200


# ── Proactive outbound — push a message to a user without them texting first ──
def send_whatsapp_alert(to_phone: str, message: str):
    """
    Use this to send alerts proactively e.g. from your Nessie transaction detector.
    to_phone: just the digits e.g. "+15718881874"
    Note: the user must have joined the sandbox first.
    """
    twilio_client.messages.create(
        body=message,
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:{to_phone}"
    )
    print(f"📤 Alert sent to {to_phone}: {message}")


# ── Test route — open in browser to push a test message to your phone ─────────
@app.route("/test-send")
def test_send():
    to = request.args.get("to")
    if not to:
        return "Usage: /test-send?to=+1YOURNUMBER", 400
    try:
        send_whatsapp_alert(to, "👋 Hello from your WhatsApp chatbot! It's working.")
        return f"✅ Sent to whatsapp:{to}", 200
    except Exception as e:
        return f"❌ Failed: {e}", 500


if __name__ == "__main__":
    print("✅ WhatsApp chatbot starting on port 8080...")
    print("   Make sure ngrok is running: ngrok http 8080")
    print("   Make sure webhook URL is set in Twilio Console:")
    print("   Messaging → Try it out → Send a WhatsApp message → Sandbox Settings")
    print("   Then WhatsApp the sandbox number to chat!\n")
    app.run(debug=True, port=8080)