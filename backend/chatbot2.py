"""Tool-calling chatbot using OpenAI's function calling API.

The chatbot has access to a set of tools it can invoke to answer
the user's financial questions. Tool definitions are standard
JSON-schema objects passed to the OpenAI chat completions API.
"""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from db import get_supabase
from helpers import get_user_budgets, get_transaction_history

load_dotenv()

_client = None

SYSTEM_PROMPT = """You are a real-time financial copilot. You help users understand their finances and make better spending decisions.

Rules:
- Use your tools to look up real data before answering. NEVER guess or fabricate numbers.
- Be concise and direct (3-5 sentences).
- Give specific, actionable advice grounded in the data you retrieved.
- Never give investment advice (buy/sell stocks).
- Supportive tone, not judgmental.
- If you don't have enough information, say so and suggest what the user can do."""

# ── Tool definitions ────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_transaction_history",
            "description": "Get the user's recent transaction history. Returns a list of transactions with amount, type (purchase/deposit), description, and date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of transactions to return (default 20)",
                    },
                },
                "required": [],
            },
        },
    },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "get_account_balances",
    #         "description": "Get the user's account balances. Returns each account's type and current balance, plus total balance.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {},
    #             "required": [],
    #         },
    #     },
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "get_budgets",
    #         "description": "Get the user's budgets. Returns each budget's category, spending limit (amount), start and end dates.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {},
    #             "required": [],
    #         },
    #     },
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "get_spending_by_category",
    #         "description": "Calculate total spending grouped by transaction description/category over recent transactions.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "limit": {
    #                     "type": "integer",
    #                     "description": "Number of recent transactions to analyze (default 50)",
    #                 },
    #             },
    #             "required": [],
    #         },
    #     },
    # },
    # {
    #     "type": "function",
    #     "function": {
    #         "name": "get_financial_summary",
    #         "description": "Get the user's financial profile including monthly income, monthly expenses target, savings goal, current savings, and debt.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {},
    #             "required": [],
    #         },
    #     },
    # },
]

# ── Tool implementations ────────────────────────────────────────────

def _exec_get_transaction_history(user_id, args):
    limit = args.get("limit", 20)
    txns = get_transaction_history(user_id, limit=limit)
    return {"transactions": txns, "count": len(txns)}


# def _exec_get_account_balances(user_id, _args):
#     sb = get_supabase()
#     accounts = sb.table("accounts").select("type, balance").eq("user_id", user_id).execute()
#     acct_list = accounts.data or []
#     total = sum(float(a.get("balance") or 0) for a in acct_list)
#     return {
#         "accounts": [{"type": a["type"], "balance": float(a.get("balance") or 0)} for a in acct_list],
#         "total_balance": total,
#     }


# def _exec_get_budgets(user_id, _args):
#     budgets = get_user_budgets(user_id)
#     return {
#         "budgets": [
#             {
#                 "category": b["category"],
#                 "amount": float(b.get("amount") or 0),
#                 "start_date": b.get("start_date"),
#                 "end_date": b.get("end_date"),
#             }
#             for b in budgets
#         ],
#     }


# def _exec_get_spending_by_category(user_id, args):
#     sb = get_supabase()
#     limit = args.get("limit", 50)

#     accounts = sb.table("accounts").select("id").eq("user_id", user_id).execute()
#     account_ids = [a["id"] for a in (accounts.data or [])]
#     if not account_ids:
#         return {"categories": {}, "total_spending": 0}

#     txns = (
#         sb.table("transactions")
#         .select("amount, type, description")
#         .in_("account_id", account_ids)
#         .eq("type", "purchase")
#         .order("transaction_date", desc=True)
#         .limit(limit)
#         .execute()
#     )

#     by_cat = {}
#     for t in (txns.data or []):
#         desc = (t.get("description") or "Other").strip()
#         by_cat[desc] = by_cat.get(desc, 0) + float(t["amount"])

#     sorted_cats = dict(sorted(by_cat.items(), key=lambda x: -x[1]))
#     return {"categories": sorted_cats, "total_spending": sum(by_cat.values())}


# def _exec_get_financial_summary(user_id, _args):
#     sb = get_supabase()
#     user = sb.table("users").select("*").eq("id", user_id).execute()
#     if not user.data:
#         return {"error": "User not found"}
#     u = user.data[0]
#     return {
#         "first_name": u.get("first_name"),
#         "monthly_income": float(u.get("monthly_income") or 0),
#         "monthly_expenses": float(u.get("monthly_expenses") or 0),
#         "savings_goal": float(u.get("savings_goal") or 0),
#         "current_savings": float(u.get("current_savings") or 0),
#         "debt": float(u.get("debt") or 0),
#     }


TOOL_DISPATCH = {
    "get_transaction_history": _exec_get_transaction_history,
    # "get_account_balances": _exec_get_account_balances,
    # "get_budgets": _exec_get_budgets,
    # "get_spending_by_category": _exec_get_spending_by_category,
    # "get_financial_summary": _exec_get_financial_summary,
}

# ── Chat loop ───────────────────────────────────────────────────────

def chat(user_id, message, channel="web"):
    """Process a user message with the tool-calling chatbot.

    Returns:
        {
            "response": str,
            "tool_calls": [ { "tool": str, "args": dict, "result": dict } ... ],
        }
    """
    sb = get_supabase()

    # Store user message
    sb.table("messages").insert({
        "user_id": user_id, "role": "user", "channel": channel, "content": message,
    }).execute()

    # Build conversation from history
    history = _get_chat_history(sb, user_id, channel, limit=10)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    client = _get_openai_client()
    if client is None:
        fallback = "I need an OpenAI API key to function. Please set OPENAI_API_KEY in your .env file."
        return {"response": fallback, "tool_calls": []}

    tool_calls_log = []

    # Loop: let the model call tools until it produces a final text response
    for _ in range(5):  # max 5 rounds of tool calling
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=500 if channel == "web" else 300,
            temperature=0.7,
        )

        choice = resp.choices[0]

        if choice.finish_reason == "tool_calls" or choice.message.tool_calls:
            messages.append(choice.message)

            for tc in choice.message.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments) if tc.function.arguments else {}

                executor = TOOL_DISPATCH.get(fn_name)
                if executor:
                    result = executor(user_id, fn_args)
                else:
                    result = {"error": f"Unknown tool: {fn_name}"}

                tool_calls_log.append({
                    "tool": fn_name,
                    "args": fn_args,
                    "result": result,
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })
        else:
            # Final text response
            response_text = choice.message.content or ""
            break
    else:
        response_text = "I wasn't able to complete my analysis. Please try rephrasing your question."

    # Store assistant response
    sb.table("messages").insert({
        "user_id": user_id, "role": "assistant", "channel": channel, "content": response_text,
    }).execute()

    return {
        "response": response_text,
        "tool_calls": tool_calls_log,
    }


def _get_chat_history(sb, user_id, channel, limit=5):
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


def _get_openai_client():
    global _client
    if _client is None:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return None
        _client = OpenAI(api_key=key)
    return _client
