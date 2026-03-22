"""Conversation Agent

Orchestrates a multi-agent reasoning pipeline for each user message:
  1. Context Gathering — pull financial data from Supabase
  2. Goals Agent — evaluate against user's financial goals
  3. Tradeoffs Agent — find alternatives and cuts
  4. Response Agent (LLM) — synthesize into a final response

Each step is traced so the frontend can display the reasoning loop.
"""

import os
import time
from datetime import datetime, timezone
from openai import OpenAI
from dotenv import load_dotenv

from db import get_supabase
from agents.goals_agent import evaluate_against_goals
from agents.tradeoffs_agent import find_tradeoffs

load_dotenv()

_client = None

SYSTEM_PROMPT = """You are a real-time financial copilot. You have access to the outputs
of two specialist agents — a Goals Agent and a Tradeoffs Agent — plus the user's
full financial context.

Rules:
- Synthesize the goals analysis and tradeoff suggestions into a single coherent response
- Be concise and direct (3-5 sentences for web, 2-3 for SMS)
- Always reference actual numbers from the context
- Give specific, actionable advice
- If the tradeoffs agent found alternatives, mention the best 1-2
- If the goals agent found conflicts, flag them clearly
- Never fabricate numbers — only use what's provided
- Never give investment advice
- Supportive tone, not judgmental"""


def _ts():
    return datetime.now(timezone.utc).isoformat()


def handle_message(user_id, message, channel="web"):
    """Process a user message through the full agent pipeline.

    Returns:
        {
            "response": str,
            "trace": [ { agent, status, ... } ... ],
        }
    """
    sb = get_supabase()
    trace = []

    # ── Step 1: Context Gathering Agent ─────────────────────────
    t0 = time.time()
    context = _build_context(sb, user_id)
    dur = int((time.time() - t0) * 1000)

    user_info = context.get("user", {})
    n_txns = len(context.get("recent_transactions", []))
    balance = context.get("total_balance", 0)

    trace.append({
        "agent": "Context Gathering Agent",
        "status": "success",
        "timestamp": _ts(),
        "duration_ms": dur,
        "input_summary": f'User message: "{_truncate(message, 60)}"',
        "output_summary": (
            f"Balance: ${balance:,.2f}, {n_txns} recent transactions, "
            f"{len(context.get('budgets', []))} budget(s)"
        ),
        "details": {
            "balance": balance,
            "accounts": len(context.get("accounts", [])),
            "transactions": n_txns,
            "budgets": len(context.get("budgets", [])),
            "has_goals": bool(user_info.get("savings_goal")),
            "has_risk_data": context.get("latest_risk") is not None,
        },
    })

    # Store the user message
    sb.table("messages").insert({
        "user_id": user_id,
        "role": "user",
        "channel": channel,
        "content": message,
    }).execute()

    # ── Step 2: Goals Agent ─────────────────────────────────────
    t0 = time.time()
    goals_result = evaluate_against_goals(context, message)
    dur = int((time.time() - t0) * 1000)

    trace.append({
        "agent": "Goals Agent",
        "agent_type": "llm",
        "model": "gpt-4o-mini",
        "status": "success",
        "timestamp": _ts(),
        "duration_ms": dur,
        "input_summary": (
            f"Savings goal: ${float(user_info.get('savings_goal') or 0):,.0f}, "
            f"debt: ${float(user_info.get('debt') or 0):,.0f}"
        ),
        "output_summary": goals_result.get("summary", "No goals to evaluate"),
        "details": {
            "aligned": goals_result.get("aligned"),
            "goal_impacts": goals_result.get("goal_impacts", []),
            "analysis": goals_result.get("analysis", ""),
        },
    })

    # ── Step 3: Tradeoffs Agent ─────────────────────────────────
    t0 = time.time()
    tradeoffs_result = find_tradeoffs(context, message)
    dur = int((time.time() - t0) * 1000)

    trace.append({
        "agent": "Tradeoffs Agent",
        "agent_type": "llm",
        "model": "gpt-4o-mini",
        "status": "success",
        "timestamp": _ts(),
        "duration_ms": dur,
        "input_summary": f"{len(tradeoffs_result.get('cuts', []))} spending areas analyzed",
        "output_summary": tradeoffs_result.get("summary", "No tradeoffs found"),
        "details": {
            "cuts": tradeoffs_result.get("cuts", []),
            "lowest_impact": tradeoffs_result.get("lowest_impact", ""),
            "alternatives": tradeoffs_result.get("alternatives", []),
        },
    })

    # ── Step 4: Response Synthesis Agent (LLM) ──────────────────
    history = _get_chat_history(sb, user_id, channel, limit=10)

    t0 = time.time()
    response_text = _generate_response(
        message, context, goals_result, tradeoffs_result, history, channel
    )
    dur = int((time.time() - t0) * 1000)

    trace.append({
        "agent": "Response Synthesis Agent",
        "agent_type": "llm",
        "model": "gpt-4o-mini",
        "status": "success",
        "timestamp": _ts(),
        "duration_ms": dur,
        "input_summary": "Goals analysis + tradeoffs + context + chat history",
        "output_summary": _truncate(response_text, 100),
        "details": {
            "response_length": len(response_text),
            "channel": channel,
            "history_messages": len(history),
        },
    })

    # Store the assistant response
    sb.table("messages").insert({
        "user_id": user_id,
        "role": "assistant",
        "channel": channel,
        "content": response_text,
    }).execute()

    return {
        "response": response_text,
        "trace": trace,
    }


# ── Context builder ─────────────────────────────────────────────────

def _build_context(sb, user_id):
    user = sb.table("users").select("*").eq("id", user_id).execute()
    if not user.data:
        return {}
    user = user.data[0]

    accounts = sb.table("accounts").select("*").eq("user_id", user_id).execute()
    account_list = accounts.data or []
    total_balance = sum(float(a.get("balance") or 0) for a in account_list)

    snapshot = (
        sb.table("snapshots")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    latest_snapshot = snapshot.data[0] if snapshot.data else None

    account_ids = [a["id"] for a in account_list]
    recent_txns = []
    if account_ids:
        recent_txns = (
            sb.table("transactions")
            .select("*")
            .in_("account_id", account_ids)
            .order("transaction_date", desc=True)
            .limit(15)
            .execute()
        ).data

    budgets = (sb.table("budgets").select("*").eq("user_id", user_id).execute()).data or []

    recent_alerts = (
        sb.table("alerts")
        .select("*")
        .eq("user_id", user_id)
        .order("sent_at", desc=True)
        .limit(5)
        .execute()
    ).data or []

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
            {"category": b["category"], "amount": b.get("amount"), "start_date": b.get("start_date"), "end_date": b.get("end_date"), "account_id": b.get("account_id")}
            for b in budgets
        ],
        "latest_risk": latest_snapshot.get("data") if latest_snapshot else None,
        "recent_alerts": [
            {"message": a["message"], "risk_level": a.get("risk_level"), "sent_at": a.get("sent_at")}
            for a in recent_alerts
        ],
    }


def _get_chat_history(sb, user_id, channel, limit=10):
    result = (
        sb.table("messages")
        .select("role, content")
        .eq("user_id", user_id)
        .eq("channel", channel)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(result.data)) if result.data else []


# ── Response generation ─────────────────────────────────────────────

def _generate_response(message, context, goals_result, tradeoffs_result, history, channel):
    client = _get_openai_client()
    if client is None:
        return _fallback_response(message, context, goals_result, tradeoffs_result)

    length_hint = "Keep your response to 2-3 sentences." if channel == "sms" else "Keep your response to 3-5 sentences."
    user = context.get("user", {})

    agent_context = f"""=== Financial Context ===
Balance: ${context.get('total_balance', 0):,.2f}
Monthly income: ${float(user.get('monthly_income') or 0):,.2f}
Monthly expenses target: ${float(user.get('monthly_expenses') or 0):,.2f}
Savings goal: ${float(user.get('savings_goal') or 0):,.2f}
Current savings: ${float(user.get('current_savings') or 0):,.2f}

Recent transactions:
{_format_txns(context.get('recent_transactions', []))}

=== Goals Agent Analysis ===
Aligned: {goals_result.get('aligned', 'N/A')}
{goals_result.get('analysis', 'No analysis.')}

=== Tradeoffs Agent Analysis ===
{tradeoffs_result.get('lowest_impact', '')}

Alternatives:
{chr(10).join('- ' + a for a in tradeoffs_result.get('alternatives', [])) or 'None'}

Potential cuts:
{chr(10).join(f"- {c['category']}: cut ${c['suggested_cut']:,.2f} from ${c['current_spend']:,.2f}" for c in tradeoffs_result.get('cuts', [])[:3]) or 'None identified'}

=== Instructions ===
{length_hint}
Synthesize the above into a helpful response. Reference the goals and tradeoff analyses."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": agent_context},
    ]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=300 if channel == "sms" else 500,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return _fallback_response(message, context, goals_result, tradeoffs_result)


def _get_openai_client():
    global _client
    if _client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return None
        _client = OpenAI(api_key=key)
    return _client


# ── Fallbacks ───────────────────────────────────────────────────────

def _fallback_response(message, context, goals_result, tradeoffs_result):
    balance = context.get("total_balance", 0)
    parts = [f"Your balance is ${balance:,.2f}."]

    if goals_result and not goals_result.get("aligned", True):
        parts.append("This conflicts with your financial goals.")
    elif goals_result:
        parts.append("This aligns with your current goals.")

    alts = tradeoffs_result.get("alternatives", []) if tradeoffs_result else []
    if alts:
        parts.append(f"Alternative: {alts[0]}")

    lowest = tradeoffs_result.get("lowest_impact", "") if tradeoffs_result else ""
    if lowest:
        parts.append(lowest)

    return " ".join(parts)


def _format_txns(txns):
    if not txns:
        return "None"
    return "\n".join(
        f"- ${t['amount']:,.2f} {t['type']} — {t.get('description') or 'Unknown'}"
        for t in txns[:8]
    )


def _truncate(s, n):
    return s[:n] + "..." if len(s) > n else s
