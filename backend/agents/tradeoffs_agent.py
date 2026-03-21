"""Tradeoffs Agent

Instead of just saying "bad idea", this agent reasons about alternatives:
- What can be cut to make room for this purchase?
- What is the lowest-impact adjustment?
- What alternative achieves the same goal?

Uses deterministic analysis for spending data + LLM for creative alternatives.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = None


def find_tradeoffs(context, message):
    """Analyze tradeoffs for a user's spending decision.

    Returns:
        {
            "cuts": [ { category, current_spend, suggested_cut, impact } ... ],
            "lowest_impact": str,
            "alternatives": [ str ... ],
            "summary": str,
        }
    """
    balance = context.get("total_balance", 0)
    txns = context.get("recent_transactions", [])
    budgets = context.get("budgets", [])
    user = context.get("user", {})
    monthly_income = float(user.get("monthly_income") or 0)

    # Group spending by description (proxy for category since Nessie lacks categories)
    spend_by_desc = {}
    for t in txns:
        if t.get("type") != "purchase":
            continue
        desc = (t.get("description") or "Other").strip()
        spend_by_desc[desc] = spend_by_desc.get(desc, 0) + t["amount"]

    # Sort by spend, highest first — these are the best candidates to cut
    sorted_spend = sorted(spend_by_desc.items(), key=lambda x: -x[1])

    cuts = []
    for desc, amount in sorted_spend[:5]:
        # Suggest cutting 30-50% of each category
        cut_amount = round(amount * 0.4, 2)
        cuts.append({
            "category": desc,
            "current_spend": round(amount, 2),
            "suggested_cut": cut_amount,
            "impact": f"Save ${cut_amount:,.2f} by reducing {desc} spending by ~40%",
        })

    # Find lowest-impact cut (smallest absolute dollar cut that still helps)
    if cuts:
        lowest = min(cuts, key=lambda c: c["suggested_cut"])
        lowest_impact = (
            f"Lowest-impact adjustment: reduce {lowest['category']} "
            f"by ${lowest['suggested_cut']:,.2f} (from ${lowest['current_spend']:,.2f})"
        )
    else:
        lowest_impact = "Not enough transaction data to identify specific cuts."

    total_cuttable = sum(c["suggested_cut"] for c in cuts)
    summary = f"Found {len(cuts)} spending area(s) with ${total_cuttable:,.2f} in potential savings."

    # Use LLM for creative alternatives
    alternatives = _llm_alternatives(context, message, cuts)

    return {
        "cuts": cuts,
        "lowest_impact": lowest_impact,
        "alternatives": alternatives,
        "summary": summary,
    }


def _llm_alternatives(context, message, cuts):
    client = _get_client()
    if not client:
        return _fallback_alternatives(cuts)

    user = context.get("user", {})
    balance = context.get("total_balance", 0)

    cuts_text = "\n".join(
        f"- {c['category']}: spending ${c['current_spend']:,.2f}, could cut ${c['suggested_cut']:,.2f}"
        for c in cuts
    ) or "No spending data available."

    prompt = f"""The user said: "{message}"

Their situation:
- Balance: ${balance:,.0f}
- Monthly income: ${float(user.get('monthly_income') or 0):,.0f}
- Monthly expenses target: ${float(user.get('monthly_expenses') or 0):,.0f}

Their recent spending areas:
{cuts_text}

Suggest 3 specific alternatives or tradeoffs. For each:
1. What could be cut or reduced to make room?
2. What's a lower-cost alternative that achieves the same goal?
3. What's the timing adjustment (e.g., wait until payday)?

Format as a JSON array of 3 strings, each being a concise 1-sentence suggestion.
Return ONLY the JSON array, no other text."""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a financial tradeoff analyst. Return only a JSON array of 3 suggestion strings."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        import json
        text = resp.choices[0].message.content.strip()
        return json.loads(text)
    except Exception:
        return _fallback_alternatives(cuts)


def _fallback_alternatives(cuts):
    alts = []
    if cuts:
        top = cuts[0]
        alts.append(f"Cut {top['category']} by ~40% to free up ${top['suggested_cut']:,.2f}.")
    alts.append("Wait until your next paycheck to make non-essential purchases.")
    alts.append("Look for a lower-cost alternative that meets the same need.")
    return alts[:3]


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return None
        _client = OpenAI(api_key=key)
    return _client
