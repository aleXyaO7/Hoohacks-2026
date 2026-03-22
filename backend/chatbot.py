"""
chatbot.py
----------
Twilio WhatsApp chatbot with OpenAI GPT-4o-mini intent classification.

3 intents:
  BUDGET_CHECK          - how much have I spent, how much do I have left
  HYPOTHETICAL_PURCHASE - if I buy X, how does that affect my spending
  SPENDING_SUMMARY      - summarize my spending patterns

Setup:
  pip install flask twilio openai
  Get an OpenAI API key at platform.openai.com
  Run: python3 chatbot.py
  Run: ngrok http 8080
  Set ngrok URL in Twilio Console → Messaging → Try it out →
    Send a WhatsApp message → Sandbox Settings
"""

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from openai import OpenAI
import os
import json
import threading

app = Flask(__name__)

# ── Credentials ────────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID     = "PASTE_YOUR_ACCOUNT_SID_HERE"   # starts with AC
TWILIO_AUTH_TOKEN      = "PASTE_YOUR_AUTH_TOKEN_HERE"
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"          # always this for sandbox
OPENAI_API_KEY         = os.environ.get("OPENAI_API_KEY", "PASTE_YOUR_OPENAI_KEY_HERE")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Last inbound sender cache (for optional alert fallback)
_last_inbound_sender_lock = threading.Lock()
_last_inbound_sender = None


def _set_last_inbound_sender(sender: str) -> None:
    global _last_inbound_sender
    with _last_inbound_sender_lock:
        _last_inbound_sender = sender


def _get_last_inbound_sender() -> str | None:
    with _last_inbound_sender_lock:
        return _last_inbound_sender


def _normalize_whatsapp_to(to_phone: str) -> str:
    to_phone = (to_phone or "").strip()
    if to_phone.startswith("whatsapp:"):
        return to_phone
    return f"whatsapp:{to_phone}"

# ── Helper: call GPT-4o-mini with a prompt ────────────────────────────────────
def ask_openai(prompt: str, max_tokens: int = 300) -> str:
    """Single helper used by every OpenAI call in this file."""
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

# ── Intents ────────────────────────────────────────────────────────────────────
INTENT_BUDGET_CHECK          = "BUDGET_CHECK"
INTENT_HYPOTHETICAL_PURCHASE = "HYPOTHETICAL_PURCHASE"
INTENT_SPENDING_SUMMARY      = "SPENDING_SUMMARY"
INTENT_UNKNOWN               = "UNKNOWN"

# ── Demo data — replace with real Nessie calls later ──────────────────────────
DEMO_BALANCE      = 1240.50
DEMO_SPENT        = 842.10
DEMO_TRANSACTIONS = [
    {"merchant": "Starbucks",   "amount": 12.50,  "category": "food"},
    {"merchant": "Target",      "amount": 52.40,  "category": "shopping"},
    {"merchant": "Netflix",     "amount":  8.99,  "category": "subscriptions"},
    {"merchant": "Whole Foods", "amount": 34.20,  "category": "food"},
    {"merchant": "Uber",        "amount": 24.75,  "category": "transport"},
    {"merchant": "Spotify",     "amount":  9.99,  "category": "subscriptions"},
    {"merchant": "Amazon",      "amount": 67.30,  "category": "shopping"},
    {"merchant": "Chipotle",    "amount": 13.80,  "category": "food"},
    {"merchant": "Shell Gas",   "amount": 45.00,  "category": "transport"},
    {"merchant": "Apple",       "amount": 14.99,  "category": "subscriptions"},
]


# ── Step 1: Classify the incoming message ─────────────────────────────────────
def classify_intent(message: str) -> dict:
    """
    Ask GPT-4o-mini to classify the message into one of 3 intents and extract
    any relevant details (item name, amount) for hypothetical purchases.

    Returns a dict e.g.:
      { "intent": "HYPOTHETICAL_PURCHASE", "amount": 200, "item": "jacket" }
      { "intent": "BUDGET_CHECK", "amount": null, "item": null }
      { "intent": "SPENDING_SUMMARY", "amount": null, "item": null }
    """
    prompt = f"""You are a financial assistant chatbot. Classify the user's message
into exactly one of these three intents:

BUDGET_CHECK
  The user wants to know how much money they have spent, how much they have
  left, or their current balance. Examples:
  - "how much have I spent this month?"
  - "what's my balance?"
  - "how much money do I have left?"
  - "am I over budget?"

HYPOTHETICAL_PURCHASE
  The user is asking about a potential or future purchase and wants to know
  how it would affect their spending or budget. Examples:
  - "if I buy a $200 jacket, can I afford it?"
  - "what happens if I spend $50 on dinner tonight?"
  - "I want to buy AirPods for $150, is that okay?"
  - "can I afford a gym membership?"

SPENDING_SUMMARY
  The user wants a summary or breakdown of their spending habits and patterns.
  Examples:
  - "where am I spending the most?"
  - "give me a summary of my spending"
  - "what are my biggest expenses?"
  - "how does my spending look?"

Also extract these fields if present:
  amount - the dollar amount of a hypothetical purchase (number or null)
  item   - the name of the item being considered (string or null)

Respond with ONLY a raw JSON object. No markdown, no code fences, no explanation.
Examples:
{{"intent": "BUDGET_CHECK", "amount": null, "item": null}}
{{"intent": "HYPOTHETICAL_PURCHASE", "amount": 200, "item": "jacket"}}
{{"intent": "SPENDING_SUMMARY", "amount": null, "item": null}}
{{"intent": "UNKNOWN", "amount": null, "item": null}}

User message: "{message}"

JSON:"""

    raw = ask_openai(prompt, max_tokens=100)
    raw = raw.replace("```json", "").replace("```", "").strip()

    print(f"🧠 OpenAI classified: {raw}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"⚠️  Could not parse classification JSON: {raw}")
        return {"intent": INTENT_UNKNOWN, "amount": None, "item": None}


# ── Step 2: Route to the right handler ────────────────────────────────────────
def process_message(sender: str, message: str) -> str:
    if message.lower().strip() == "help":
        return (
            "💳 *FinanceBot — just ask me naturally!*\n\n"
            "Here are some things you can ask:\n\n"
            "💰 *Budget Check*\n"
            "_\"How much have I spent this month?\"_\n"
            "_\"What's my balance?\"_\n\n"
            "🛍️ *Hypothetical Purchase*\n"
            "_\"Can I afford a $200 jacket?\"_\n"
            "_\"What if I buy AirPods for $150?\"_\n\n"
            "📊 *Spending Summary*\n"
            "_\"Where am I spending the most?\"_\n"
            "_\"Give me a breakdown of my spending\"_"
        )

    classification = classify_intent(message)
    intent         = classification.get("intent", INTENT_UNKNOWN)
    amount         = classification.get("amount")
    item           = classification.get("item")

    print(f"📊 Intent: {intent} | Amount: {amount} | Item: {item}")

    if intent == INTENT_BUDGET_CHECK:
        return handle_budget_check(sender)

    elif intent == INTENT_HYPOTHETICAL_PURCHASE:
        return handle_hypothetical_purchase(sender, amount, item)

    elif intent == INTENT_SPENDING_SUMMARY:
        return handle_spending_summary(sender)

    else:
        return (
            "🤔 I didn't quite catch that. Try asking:\n\n"
            "• _\"What's my balance?\"_\n"
            "• _\"Can I afford a $100 dinner?\"_\n"
            "• _\"Where am I spending the most?\"_\n\n"
            "Or text *HELP* to see all options."
        )


# ── Handlers ───────────────────────────────────────────────────────────────────

def handle_budget_check(sender: str) -> str:
    """
    Tell the user how much they've spent and how much they have left.
    TODO: replace DEMO_* constants with real Nessie API calls.
    """
    balance   = DEMO_BALANCE
    spent     = DEMO_SPENT
    remaining = balance - spent
    num_txns  = len(DEMO_TRANSACTIONS)

    prompt = (
        f"Write a clear, friendly WhatsApp message giving the user their budget check. "
        f"Their account balance is ${balance:.2f}. "
        f"They have spent ${spent:.2f} this month across {num_txns} transactions. "
        f"They have ${remaining:.2f} remaining. "
        f"Be concise — 3 sentences max. Use 1-2 emojis. "
        f"Use WhatsApp bold (*text*) for every dollar amount."
    )

    return ask_openai(prompt)


def handle_hypothetical_purchase(
    sender: str,
    amount: float | None,
    item: str | None
) -> str:
    """
    Tell the user how a potential purchase would affect their spending.
    TODO: replace DEMO_* constants with real Nessie API calls.
    """
    if not amount:
        return (
            "🛍️ Tell me more about what you want to buy!\n\n"
            "For example:\n"
            "_\"Can I afford a $200 jacket?\"_\n"
            "_\"What if I spend $80 on dinner?\"_"
        )

    balance        = DEMO_BALANCE
    spent          = DEMO_SPENT
    remaining      = balance - spent
    after_purchase = remaining - amount
    can_afford     = after_purchase >= 0
    item_str       = f"a {item}" if item else f"this ${amount:.2f} purchase"

    # Build per-category context so OpenAI can comment on spending impact
    category_totals: dict = {}
    for txn in DEMO_TRANSACTIONS:
        cat = txn["category"]
        category_totals[cat] = category_totals.get(cat, 0) + txn["amount"]

    category_lines = "\n".join(
        f"  {cat.title()}: ${total:.2f}"
        for cat, total in sorted(category_totals.items(), key=lambda x: -x[1])
    )

    prompt = (
        f"The user is thinking about buying {item_str} for ${amount:.2f}.\n\n"
        f"Their financial situation:\n"
        f"  Account balance: ${balance:.2f}\n"
        f"  Spent this month: ${spent:.2f}\n"
        f"  Remaining before purchase: ${remaining:.2f}\n"
        f"  Remaining after purchase: ${after_purchase:.2f}\n"
        f"  Can they afford it: {'Yes' if can_afford else 'No — would go over balance'}\n\n"
        f"Current spending by category:\n{category_lines}\n\n"
        f"Write a friendly, direct 3-4 sentence WhatsApp message advising them "
        f"on whether this is a good idea. Include what their balance would be after "
        f"the purchase. Be honest if it's a bad idea. Use 1-2 emojis. "
        f"Use WhatsApp bold (*text*) for all dollar amounts."
    )

    return ask_openai(prompt)


def handle_spending_summary(sender: str) -> str:
    """
    Summarize the user's spending patterns across categories.
    TODO: replace DEMO_TRANSACTIONS with real Nessie purchases.
    """
    category_totals: dict = {}
    for txn in DEMO_TRANSACTIONS:
        cat = txn["category"]
        category_totals[cat] = category_totals.get(cat, 0) + txn["amount"]

    total_spent = sum(category_totals.values())

    breakdown_lines = []
    for cat, total in sorted(category_totals.items(), key=lambda x: -x[1]):
        pct = (total / total_spent * 100) if total_spent > 0 else 0
        breakdown_lines.append(f"  {cat.title()}: ${total:.2f} ({pct:.0f}%)")

    breakdown = "\n".join(breakdown_lines)

    top_merchants = sorted(DEMO_TRANSACTIONS, key=lambda x: -x["amount"])[:3]
    merchant_lines = "\n".join(
        f"  {t['merchant']}: ${t['amount']:.2f}" for t in top_merchants
    )

    prompt = (
        f"Write a friendly spending summary WhatsApp message for the user.\n\n"
        f"Total spent this month: ${total_spent:.2f}\n\n"
        f"Spending by category:\n{breakdown}\n\n"
        f"Top 3 merchants by spend:\n{merchant_lines}\n\n"
        f"Write 3-4 sentences: first give an overall summary, then highlight the "
        f"biggest spending category, then give one practical tip based on their patterns. "
        f"Use 1-2 emojis. Use WhatsApp bold (*text*) for all dollar amounts and "
        f"category names."
    )

    return ask_openai(prompt)


# ── Incoming WhatsApp webhook ──────────────────────────────────────────────────
@app.route("/sms", methods=["POST"])
def incoming_message():
    sender       = request.form.get("From", "")
    user_message = request.form.get("Body", "").strip()

    if sender:
        _set_last_inbound_sender(sender)

    print(f"\n📱 [{sender}]: {user_message}")

    try:
        reply = process_message(sender, user_message)
    except Exception as e:
        print(f"❌ Error processing message: {e}")
        reply = "Sorry, something went wrong. Please try again."

    print(f"📤 Reply: {reply}\n")

    resp = MessagingResponse()
    resp.message(reply)
    return str(resp), 200, {"Content-Type": "text/xml"}


# ── Health check ───────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return "✅ WhatsApp FinanceBot with GPT-4o-mini is running!", 200


# ── Proactive alert ────────────────────────────────────────────────────────────
def send_whatsapp_alert(to_phone: str | None, message: str):
    """
    Push a WhatsApp message to a user proactively e.g. new transaction alert.
    to_phone: just the number e.g. "+15718881874"
    User must have joined the sandbox first.
    """
    target = to_phone or _get_last_inbound_sender()
    if not target:
        raise ValueError(
            "No destination phone available. Pass to_phone, or receive at least one inbound /sms first."
        )

    twilio_client.messages.create(
        body=message,
        from_=TWILIO_WHATSAPP_NUMBER,
        to=_normalize_whatsapp_to(target)
    )
    print(f"📤 Alert sent to {target}: {message}")

def send_over_budget_alert(
    to_phone: str | None,
    merchant: str,
    purchase_amount: float,
    budget_limit: float,
    category: str,
):
    """
    Send a proactive WhatsApp alert when a purchase exceeds the recommended
    budget for that category.

    Args:
        to_phone:        user's phone number e.g. "+15718881874"
        merchant:        name of the merchant e.g. "Starbucks"
        purchase_amount: how much the purchase was e.g. 52.40
        budget_limit:    the recommended/set budget for this category e.g. 30.00
        category:        spending category e.g. "food"

    Example call:
        send_over_budget_alert("+15718881874", "Starbucks", 52.40, 30.00, "food")
    """
    overage = purchase_amount - budget_limit

    prompt = (
        f"Write a short, friendly WhatsApp alert message telling the user that "
        f"their recent purchase of ${purchase_amount:.2f} at {merchant} has exceeded "
        f"their recommended {category} budget of ${budget_limit:.2f} by ${overage:.2f}. "
        f"Suggest they be mindful of further spending in this category. "
        f"Keep it to 2-3 sentences. Use 1 emoji. "
        f"Use WhatsApp bold (*text*) for all dollar amounts and the merchant name."
    )

    message = ask_openai(prompt, max_tokens=150)

    target = to_phone or _get_last_inbound_sender()
    if not target:
        raise ValueError(
            "No destination phone available. Pass to_phone, or receive at least one inbound /sms first."
        )

    twilio_client.messages.create(
        body=message,
        from_=TWILIO_WHATSAPP_NUMBER,
        to=_normalize_whatsapp_to(target)
    )
    print(f"📤 Over-budget alert sent to {target}: {message}")


# ── Test route ─────────────────────────────────────────────────────────────────
@app.route("/test-send")
def test_send():
    to = request.args.get("to")
    try:
        send_whatsapp_alert(to, "👋 Hello from your WhatsApp FinanceBot!")
        destination = to or _get_last_inbound_sender()
        return f"✅ Sent to {_normalize_whatsapp_to(destination)}", 200
    except Exception as e:
        return (
            f"❌ Failed: {e}. Use /test-send?to=+1YOURNUMBER or send one inbound message first.",
            500,
        )


if __name__ == "__main__":
    print("✅ WhatsApp FinanceBot starting on port 8080...")
    print("   Make sure OPENAI_API_KEY is set in your environment")
    print("   Make sure ngrok is running: ngrok http 8080")
    print("   Set webhook in: Twilio Console → Sandbox Settings\n")
    app.run(debug=True, port=8080)