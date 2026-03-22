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
from helpers import get_user_budgets, get_transaction_history, create_budget

load_dotenv()

_client = None

SYSTEM_PROMPT = """You are BudgetLess, a real-time financial assistant. You help users understand their finances and make better spending decisions.

Rules:
- Use your tools to look up real data before answering. NEVER guess or fabricate numbers.
- For budgets: use get_budget_history to list them; use set_budget to create or update a budget (same category updates the existing row). Dates must be YYYY-MM-DD.
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
    {
        "type": "function",
        "function": {
            "name": "get_budget_history",
            "description": "List all of the user's budgets from Supabase (spending limits by category), most recently created first. Each row includes category, amount limit, start/end dates, and when it was created.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_budget",
            "description": "Create a new budget or update an existing one for the same category. Writes to Supabase. If a budget already exists for this category, it is updated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Budget category name (e.g. food, transport, shopping). Must match transaction categories for alerts to work.",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Spending limit in dollars for the period",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Period start as YYYY-MM-DD",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Period end as YYYY-MM-DD",
                    },
                    "account_id": {
                        "type": "string",
                        "description": "Optional Supabase account UUID to scope this budget to one account",
                    },
                },
                "required": ["category", "amount", "start_date", "end_date"],
            },
        },
    },
]

# ── Tool implementations ────────────────────────────────────────────

def _exec_get_transaction_history(user_id, args):
    try:
        limit = int(args.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))
    txns = get_transaction_history(user_id, limit=limit)
    return {"transactions": txns, "count": len(txns)}


def _exec_get_budget_history(user_id, _args):
    budgets = get_user_budgets(user_id)
    rows = []
    for b in budgets:
        rows.append({
            "id": b.get("id"),
            "category": b.get("category"),
            "amount": float(b.get("amount") or 0),
            "start_date": b.get("start_date"),
            "end_date": b.get("end_date"),
            "account_id": b.get("account_id"),
            "created_at": b.get("created_at"),
        })
    rows.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return {"budgets": rows, "count": len(rows)}


def _exec_set_budget(user_id, args):
    category = (args.get("category") or "").strip()
    if not category:
        return {"error": "category is required"}
    try:
        amount = float(args["amount"])
    except (KeyError, TypeError, ValueError):
        return {"error": "amount must be a number"}
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    if not start_date or not end_date:
        return {"error": "start_date and end_date are required (YYYY-MM-DD)"}
    account_id = args.get("account_id")
    if account_id is not None and account_id == "":
        account_id = None
    try:
        row = create_budget(
            user_id,
            category,
            amount,
            str(start_date),
            str(end_date),
            account_id=account_id,
        )
        if not row:
            return {"error": "Failed to save budget to database"}
        return {
            "saved": True,
            "budget": {
                "id": row.get("id"),
                "category": row.get("category"),
                "amount": float(row.get("amount") or 0),
                "start_date": row.get("start_date"),
                "end_date": row.get("end_date"),
                "account_id": row.get("account_id"),
            },
        }
    except Exception as e:
        return {"error": str(e)}


TOOL_DISPATCH = {
    "get_transaction_history": _exec_get_transaction_history,
    "get_budget_history": _exec_get_budget_history,
    "set_budget": _exec_set_budget,
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
