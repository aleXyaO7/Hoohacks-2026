"""Messaging Agent (LLM)

Transforms structured risk assessments into natural-language messages.
Two modes: concise SMS (1-3 sentences) and detailed dashboard explanation.

Falls back to deterministic templates if the LLM is unavailable.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        _client = OpenAI(api_key=api_key)
    return _client


SMS_SYSTEM_PROMPT = """You are a financial copilot sending an SMS alert.
Rules:
- Maximum 2-3 sentences
- Be direct and actionable
- Reference specific numbers (balance, amounts, percentages)
- Include one clear recommendation
- Supportive tone, not judgmental
- No emojis, no hashtags
- Do NOT start with "Hey" or greetings"""

DASHBOARD_SYSTEM_PROMPT = """You are a financial copilot explaining a risk assessment on a dashboard.
Rules:
- 3-5 sentences
- Start with what's happening (situation)
- Explain why it matters (impact)
- Give specific, actionable recommendations
- Reference actual numbers from the context
- Supportive and clear tone
- You may mention multiple factors if relevant"""


def generate_alert_message(risk_assessment, channel="sms"):
    """Generate a natural-language alert message from a risk assessment.

    Args:
        risk_assessment: Output from risk_agent.assess_risk()
        channel: "sms" or "dashboard"

    Returns:
        str: The generated message
    """
    client = _get_client()
    if client is None:
        return _fallback_message(risk_assessment, channel)

    system_prompt = SMS_SYSTEM_PROMPT if channel == "sms" else DASHBOARD_SYSTEM_PROMPT

    context = risk_assessment.get("context", {})
    factors = risk_assessment.get("factors", [])
    recommendations = risk_assessment.get("recommendations", [])

    user_prompt = f"""Risk Level: {risk_assessment['risk_level'].upper()}
Risk Score: {risk_assessment['score']}/100

Financial Context:
- Balance: ${context.get('total_balance', 0):,.2f}
- Monthly spending: ${context.get('monthly_spending', 0):,.2f}
- Weekly spending: ${context.get('weekly_spending', 0):,.2f}
- Monthly income: ${context.get('monthly_income', 0):,.2f}
- Day {context.get('days_into_month', 0)} of the month

Risk Factors:
{_format_factors(factors)}

Recommended Actions:
{_format_list(recommendations)}

Generate the alert message."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=200 if channel == "sms" else 400,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return _fallback_message(risk_assessment, channel)


def generate_explanation(risk_assessment):
    """Generate a detailed explanation of a risk assessment for the dashboard.

    More verbose than an alert — walks through reasoning.
    """
    client = _get_client()
    if client is None:
        return _fallback_explanation(risk_assessment)

    context = risk_assessment.get("context", {})
    factors = risk_assessment.get("factors", [])
    recommendations = risk_assessment.get("recommendations", [])

    prompt = f"""Explain this financial risk assessment to the user in a clear, helpful way.

Risk Level: {risk_assessment['risk_level']}
Score: {risk_assessment['score']}/100

Balance: ${context.get('total_balance', 0):,.2f}
Monthly spending so far: ${context.get('monthly_spending', 0):,.2f}
Monthly income: ${context.get('monthly_income', 0):,.2f}
Transactions this month: {context.get('num_transactions_this_month', 0)}
Day {context.get('days_into_month', 0)} of the month

Factors:
{_format_factors(factors)}

Recommendations:
{_format_list(recommendations)}

Write a 4-6 sentence explanation. Be specific with numbers. Structure as: situation, impact, what to do."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a supportive financial copilot. Be clear, specific, and actionable. No fluff."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return _fallback_explanation(risk_assessment)


# ── Fallbacks (no LLM needed) ──────────────────────────────────────

def _fallback_message(risk, channel):
    level = risk["risk_level"].upper()
    score = risk["score"]
    factors = risk.get("factors", [])
    recs = risk.get("recommendations", [])
    balance = risk["context"].get("total_balance", 0)

    top_factor = factors[0]["detail"] if factors else "Financial risk detected"
    top_rec = recs[0] if recs else "Review your spending."

    if channel == "sms":
        return f"{top_factor}. Balance: ${balance:,.2f}. {top_rec}"
    else:
        lines = [f"Risk Level: {level} (score {score}/100)", f"Balance: ${balance:,.2f}"]
        for f in factors[:3]:
            lines.append(f"- {f['detail']}")
        for r in recs[:2]:
            lines.append(f"Action: {r}")
        return "\n".join(lines)


def _fallback_explanation(risk):
    factors = risk.get("factors", [])
    recs = risk.get("recommendations", [])
    context = risk.get("context", {})

    parts = [f"Your current risk level is {risk['risk_level']} (score: {risk['score']}/100)."]
    parts.append(f"Balance: ${context.get('total_balance', 0):,.2f}, "
                 f"spending ${context.get('monthly_spending', 0):,.2f} this month.")
    for f in factors[:3]:
        parts.append(f"{f['detail']}.")
    for r in recs[:2]:
        parts.append(r)
    return " ".join(parts)


# ── Formatting helpers ──────────────────────────────────────────────

def _format_factors(factors):
    if not factors:
        return "None"
    return "\n".join(
        f"- [{f['severity'].upper()}] {f['detail']}" for f in factors
    )


def _format_list(items):
    if not items:
        return "None"
    return "\n".join(f"- {item}" for item in items)
