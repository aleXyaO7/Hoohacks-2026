"""Conversation Agent

Handles user messages (from web chat or SMS webhook).
Retrieves the user's financial context, recent alerts, and chat history,
then uses the LLM to generate a contextual response.

Falls back to canned responses if the LLM is unavailable.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv
from db import get_supabase
from agents.risk_agent import assess_risk

load_dotenv()

_client = None

SYSTEM_PROMPT = """You are a real-time financial copilot. The user is chatting with you about their finances.

Rules:
- Be concise and direct
- Always reference actual numbers from their financial context
- Give specific, actionable advice
- If asked "can I afford this?", calculate based on their balance, upcoming expenses, and budget
- If asked "why did you alert me?", explain the specific risk factors
- If asked "what should I cut?", identify their highest spending categories
- Never fabricate numbers — only use what's in the context
- Never give investment advice (buy/sell stocks)
- Supportive tone, not judgmental
- For SMS channel: keep responses to 2-3 sentences max
- For web channel: can be slightly more detailed (3-5 sentences)"""


def handle_message(user_id, message, channel="web"):
    """Process an incoming user message and generate a response.

    Args:
        user_id: The user's Supabase ID
        message: The user's message text
        channel: "web" or "sms"

    Returns:
        dict with "response" (str) and "context_used" (dict)
    """
    sb = get_supabase()

    # Gather financial context
    context = _build_context(sb, user_id)

    # Store the user message
    sb.table("messages").insert({
        "user_id": user_id,
        "role": "user",
        "channel": channel,
        "content": message,
    }).execute()

    # Get recent conversation history
    history = _get_chat_history(sb, user_id, channel, limit=10)

    # Generate response
    response_text = _generate_response(message, context, history, channel)

    # Store the assistant response
    sb.table("messages").insert({
        "user_id": user_id,
        "role": "assistant",
        "channel": channel,
        "content": response_text,
    }).execute()

    return {
        "response": response_text,
        "context_used": context,
    }


def _build_context(sb, user_id):
    """Assemble the user's full financial context for the LLM."""
    user = sb.table("users").select("*").eq("id", user_id).execute()
    if not user.data:
        return {}
    user = user.data[0]

    accounts = sb.table("accounts").select("*").eq("user_id", user_id).execute()
    account_list = accounts.data or []
    total_balance = sum(float(a.get("balance") or 0) for a in account_list)

    # Latest risk snapshot
    snapshot = (
        sb.table("snapshots")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    latest_snapshot = snapshot.data[0] if snapshot.data else None

    # Recent transactions
    account_ids = [a["id"] for a in account_list]
    recent_txns = []
    if account_ids:
        txn_result = (
            sb.table("transactions")
            .select("*")
            .in_("account_id", account_ids)
            .order("transaction_date", desc=True)
            .limit(15)
            .execute()
        )
        recent_txns = txn_result.data

    # Active budgets
    budgets = sb.table("budgets").select("*").eq("user_id", user_id).execute()

    # Recent alerts
    recent_alerts = (
        sb.table("alerts")
        .select("*")
        .eq("user_id", user_id)
        .order("sent_at", desc=True)
        .limit(5)
        .execute()
    )

    return {
        "user": {
            "first_name": user.get("first_name"),
            "monthly_income": user.get("monthly_income"),
            "monthly_expenses": user.get("monthly_expenses"),
            "savings_goal": user.get("savings_goal"),
            "current_savings": user.get("current_savings"),
            "debt": user.get("debt"),
        },
        "total_balance": total_balance,
        "accounts": [
            {"type": a["type"], "balance": float(a.get("balance") or 0)}
            for a in account_list
        ],
        "recent_transactions": [
            {
                "amount": t["amount"],
                "description": t.get("description", ""),
                "type": t["type"],
                "date": t.get("transaction_date"),
            }
            for t in recent_txns
        ],
        "budgets": [
            {
                "category": b["category"],
                "monthly_limit": b.get("monthly_limit"),
                "weekly_limit": b.get("weekly_limit"),
            }
            for b in (budgets.data or [])
        ],
        "latest_risk": latest_snapshot.get("data") if latest_snapshot else None,
        "recent_alerts": [
            {
                "message": a["message"],
                "risk_level": a.get("risk_level"),
                "sent_at": a.get("sent_at"),
            }
            for a in (recent_alerts.data or [])
        ],
    }


def _get_chat_history(sb, user_id, channel, limit=10):
    """Retrieve recent conversation messages for context."""
    result = (
        sb.table("messages")
        .select("role, content")
        .eq("user_id", user_id)
        .eq("channel", channel)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    # Reverse so oldest is first
    messages = list(reversed(result.data)) if result.data else []
    return messages


def _generate_response(message, context, history, channel):
    """Call the LLM to generate a response, with fallback."""
    client = _get_openai_client()
    if client is None:
        return _fallback_response(message, context)

    length_hint = "Keep your response to 2-3 sentences." if channel == "sms" else "Keep your response to 3-5 sentences."

    context_prompt = f"""Current Financial Context:
- Balance: ${context.get('total_balance', 0):,.2f}
- Accounts: {len(context.get('accounts', []))}
- Monthly income: ${context.get('user', {}).get('monthly_income') or 0:,.2f}
- Monthly expenses target: ${context.get('user', {}).get('monthly_expenses') or 0:,.2f}
- Savings goal: ${context.get('user', {}).get('savings_goal') or 0:,.2f}
- Current savings: ${context.get('user', {}).get('current_savings') or 0:,.2f}

Recent Transactions:
{_format_transactions(context.get('recent_transactions', []))}

Budgets:
{_format_budgets(context.get('budgets', []))}

Latest Risk Assessment:
{_format_risk(context.get('latest_risk'))}

Recent Alerts:
{_format_alerts(context.get('recent_alerts', []))}

{length_hint}"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context_prompt},
    ]

    # Add conversation history
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add the current message
    messages.append({"role": "user", "content": message})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=300 if channel == "sms" else 500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return _fallback_response(message, context)


def _get_openai_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        _client = OpenAI(api_key=api_key)
    return _client


# ── Fallback (no LLM) ──────────────────────────────────────────────

def _fallback_response(message, context):
    """Rule-based responses when the LLM is unavailable."""
    msg_lower = message.lower()
    balance = context.get("total_balance", 0)

    if "afford" in msg_lower or "can i" in msg_lower:
        return (
            f"Your current balance is ${balance:,.2f}. "
            "Based on your recent spending patterns, I'd recommend keeping "
            "non-essential purchases under $50 until your next income."
        )

    if "alert" in msg_lower or "why" in msg_lower:
        alerts = context.get("recent_alerts", [])
        if alerts:
            return f"Your most recent alert: {alerts[0]['message']}"
        return "No recent alerts found."

    if "cut" in msg_lower or "save" in msg_lower or "reduce" in msg_lower:
        risk = context.get("latest_risk")
        if risk and risk.get("recommendations"):
            return " ".join(risk["recommendations"][:2])
        return "Review your recent transactions for recurring subscriptions or dining expenses you could reduce."

    if "balance" in msg_lower or "how much" in msg_lower:
        return f"Your current total balance across all accounts is ${balance:,.2f}."

    return (
        f"Your balance is ${balance:,.2f}. "
        "I can help with questions like 'Can I afford this?', "
        "'What should I cut?', or 'Why did you alert me?'"
    )


# ── Formatting helpers ──────────────────────────────────────────────

def _format_transactions(txns):
    if not txns:
        return "No recent transactions"
    lines = []
    for t in txns[:10]:
        desc = t.get("description") or "Unknown"
        lines.append(f"- ${t['amount']:,.2f} {t['type']} — {desc} ({t.get('date', 'N/A')})")
    return "\n".join(lines)


def _format_budgets(budgets):
    if not budgets:
        return "No budgets set"
    return "\n".join(
        f"- {b['category']}: ${b.get('monthly_limit') or 0:,.2f}/month"
        for b in budgets
    )


def _format_risk(risk):
    if not risk:
        return "No risk assessment available"
    level = risk.get("risk_level") or risk.get("score", "N/A")
    factors = risk.get("factors", [])
    factor_text = "; ".join(f["detail"] for f in factors[:3]) if factors else "None"
    return f"Score: {risk.get('score', 'N/A')}/100, Factors: {factor_text}"


def _format_alerts(alerts):
    if not alerts:
        return "No recent alerts"
    return "\n".join(
        f"- [{a.get('risk_level', 'N/A')}] {a['message'][:100]}"
        for a in alerts[:3]
    )
