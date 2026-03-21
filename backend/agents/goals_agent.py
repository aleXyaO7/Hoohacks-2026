"""Goals Agent

Evaluates the user's message/decision against their stated financial goals.
Mostly deterministic math, uses LLM only for the natural-language summary.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = None


def evaluate_against_goals(context, message):
    """Assess how a user's question/decision aligns with their goals.

    Returns:
        {
            "aligned": bool,
            "analysis": str (natural language),
            "goal_impacts": [ { goal, impact, detail } ... ],
            "summary": str (one-liner),
        }
    """
    user = context.get("user", {})
    balance = context.get("total_balance", 0)

    savings_goal = float(user.get("savings_goal") or 0)
    current_savings = float(user.get("current_savings") or 0)
    monthly_income = float(user.get("monthly_income") or 0)
    monthly_expenses = float(user.get("monthly_expenses") or 0)
    debt = float(user.get("debt") or 0)

    impacts = []
    aligned = True

    # Monthly savings capacity
    savings_capacity = monthly_income - monthly_expenses
    remaining_to_goal = max(0, savings_goal - current_savings)

    if savings_capacity > 0 and remaining_to_goal > 0:
        months_to_goal = remaining_to_goal / savings_capacity
        impacts.append({
            "goal": "Savings Goal",
            "status": f"${current_savings:,.0f} of ${savings_goal:,.0f}",
            "detail": f"At current rate (${savings_capacity:,.0f}/mo), ~{months_to_goal:.0f} months to reach goal",
        })
    elif savings_capacity <= 0 and remaining_to_goal > 0:
        aligned = False
        impacts.append({
            "goal": "Savings Goal",
            "status": f"${current_savings:,.0f} of ${savings_goal:,.0f}",
            "detail": f"No savings capacity — spending exceeds income by ${abs(savings_capacity):,.0f}/mo",
        })

    # Debt consideration
    if debt > 0:
        impacts.append({
            "goal": "Debt Reduction",
            "status": f"${debt:,.0f} outstanding",
            "detail": "Additional spending increases pressure on debt repayment",
        })
        if savings_capacity <= 0:
            aligned = False

    # Balance runway
    if monthly_expenses > 0:
        runway_months = balance / monthly_expenses
        if runway_months < 1:
            aligned = False
            impacts.append({
                "goal": "Financial Safety",
                "status": f"${balance:,.0f} balance",
                "detail": f"Less than 1 month of expenses in the account ({runway_months:.1f} months)",
            })

    # Spending vs income ratio
    txns = context.get("recent_transactions", [])
    recent_spend = sum(t["amount"] for t in txns if t.get("type") == "purchase")
    if monthly_income > 0 and recent_spend > 0:
        spend_ratio = recent_spend / monthly_income
        if spend_ratio > 0.8:
            aligned = False
            impacts.append({
                "goal": "Spending Control",
                "status": f"{spend_ratio:.0%} of income spent",
                "detail": "Spending is above 80% of income, leaving little room for goals",
            })

    summary = _build_summary(aligned, impacts)

    # Use LLM for a contextual analysis if available
    analysis = _llm_analysis(context, message, impacts, aligned)

    return {
        "aligned": aligned,
        "analysis": analysis,
        "goal_impacts": impacts,
        "summary": summary,
    }


def _build_summary(aligned, impacts):
    if not impacts:
        return "No financial goals set to evaluate against."
    if aligned:
        return f"Decision aligns with goals. {len(impacts)} goal(s) evaluated."
    return f"Decision conflicts with {sum(1 for i in impacts if 'No savings' in i['detail'] or 'exceeds' in i['detail'] or 'Less than' in i['detail'])} goal(s)."


def _llm_analysis(context, message, impacts, aligned):
    client = _get_client()
    if not client:
        return _fallback_analysis(impacts, aligned)

    impact_text = "\n".join(
        f"- {i['goal']}: {i['status']} — {i['detail']}" for i in impacts
    ) or "No goals set."

    user = context.get("user", {})
    prompt = f"""The user asked: "{message}"

Their financial goals:
- Savings goal: ${float(user.get('savings_goal') or 0):,.0f} (current: ${float(user.get('current_savings') or 0):,.0f})
- Monthly income: ${float(user.get('monthly_income') or 0):,.0f}
- Monthly expenses target: ${float(user.get('monthly_expenses') or 0):,.0f}
- Debt: ${float(user.get('debt') or 0):,.0f}
- Balance: ${context.get('total_balance', 0):,.0f}

Goal impact analysis:
{impact_text}

Overall alignment: {"ALIGNED" if aligned else "CONFLICTS"}

Write a 2-3 sentence assessment of how this decision affects their goals. Be specific with numbers."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a financial goals analyst. Be concise, specific, and reference actual numbers."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.5,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return _fallback_analysis(impacts, aligned)


def _fallback_analysis(impacts, aligned):
    if not impacts:
        return "No financial goals configured to evaluate."
    parts = ["Aligned with goals." if aligned else "Conflicts with current goals."]
    for i in impacts[:2]:
        parts.append(f"{i['goal']}: {i['detail']}.")
    return " ".join(parts)


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return None
        _client = OpenAI(api_key=key)
    return _client
