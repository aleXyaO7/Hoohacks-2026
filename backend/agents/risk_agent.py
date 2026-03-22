"""Financial Risk Agent

Pure deterministic logic — no LLM. Evaluates a user's full financial
picture and produces a structured risk assessment with score, factors,
and actionable recommendations.
"""

from datetime import datetime, timezone, timedelta
from db import get_supabase


# ── Scoring weights ─────────────────────────────────────────────────

WEIGHT_BALANCE = 30
WEIGHT_BUDGET = 25
WEIGHT_CASH_FLOW = 25
WEIGHT_GOALS = 20


def assess_risk(user_id):
    """Run a full risk assessment for a user.

    Returns:
        {
            "risk_level": "low" | "medium" | "high" | "critical",
            "score": 0-100 (higher = more risk),
            "factors": [ { factor, severity, detail } ... ],
            "recommendations": [ str ... ],
            "context": { ... financial summary ... },
        }
    """
    sb = get_supabase()

    user = sb.table("users").select("*").eq("id", user_id).execute()
    if not user.data:
        return {"error": "User not found"}
    user = user.data[0]

    accounts = (
        sb.table("accounts").select("*").eq("user_id", user_id).execute()
    )
    account_list = accounts.data or []
    account_ids = [a["id"] for a in account_list]

    total_balance = sum(float(a.get("balance") or 0) for a in account_list)

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=now.weekday())

    # Fetch this month's transactions across all accounts
    month_txns = _get_transactions_since(sb, account_ids, month_start.strftime("%Y-%m-%d"))
    week_txns = _get_transactions_since(sb, account_ids, week_start.strftime("%Y-%m-%d"))

    monthly_spending = sum(t["amount"] for t in month_txns if t["type"] == "purchase")
    weekly_spending = sum(t["amount"] for t in week_txns if t["type"] == "purchase")
    monthly_income = sum(t["amount"] for t in month_txns if t["type"] == "deposit")

    budgets = (
        sb.table("budgets").select("*").eq("user_id", user_id).execute()
    ).data or []

    # ── Compute each risk factor ────────────────────────────────

    factors = []
    recommendations = []

    balance_score = _score_balance(total_balance, monthly_spending, factors, recommendations)
    budget_score = _score_budgets(sb, account_ids, budgets, month_start, factors, recommendations)
    cash_flow_score = _score_cash_flow(
        user, total_balance, monthly_spending, monthly_income, factors, recommendations
    )
    goal_score = _score_goals(user, total_balance, monthly_spending, monthly_income, factors, recommendations)

    # ── Weighted total ──────────────────────────────────────────

    total_score = (
        balance_score * WEIGHT_BALANCE
        + budget_score * WEIGHT_BUDGET
        + cash_flow_score * WEIGHT_CASH_FLOW
        + goal_score * WEIGHT_GOALS
    ) / 100

    total_score = max(0, min(100, total_score))

    if total_score >= 75:
        risk_level = "critical"
    elif total_score >= 50:
        risk_level = "high"
    elif total_score >= 25:
        risk_level = "medium"
    else:
        risk_level = "low"

    context = {
        "total_balance": total_balance,
        "monthly_spending": monthly_spending,
        "weekly_spending": weekly_spending,
        "monthly_income": monthly_income,
        "monthly_expenses_goal": float(user.get("monthly_expenses") or 0),
        "savings_goal": float(user.get("savings_goal") or 0),
        "num_accounts": len(account_list),
        "num_transactions_this_month": len(month_txns),
        "days_into_month": now.day,
    }

    return {
        "risk_level": risk_level,
        "score": round(total_score, 1),
        "factors": factors,
        "recommendations": recommendations,
        "context": context,
    }


# ── Scoring functions (each returns 0-100, higher = worse) ──────────

def _score_balance(total_balance, monthly_spending, factors, recommendations):
    if total_balance <= 0:
        factors.append({"factor": "zero_balance", "severity": "critical",
                        "detail": f"Balance is ${total_balance:.2f}"})
        recommendations.append("Immediate action needed — balance is at or below zero.")
        return 100

    if monthly_spending > 0:
        runway_days = (total_balance / (monthly_spending / 30))
    else:
        runway_days = 999

    if runway_days < 7:
        factors.append({"factor": "low_runway", "severity": "critical",
                        "detail": f"~{runway_days:.0f} days of spending left at current rate"})
        recommendations.append(f"At current pace you have ~{runway_days:.0f} days of funds left. Cut non-essential spending now.")
        return 90
    elif runway_days < 14:
        factors.append({"factor": "low_runway", "severity": "high",
                        "detail": f"~{runway_days:.0f} days of spending left"})
        recommendations.append(f"About {runway_days:.0f} days of funds remaining — slow down discretionary spending.")
        return 65
    elif runway_days < 30:
        factors.append({"factor": "moderate_runway", "severity": "medium",
                        "detail": f"~{runway_days:.0f} days of spending left"})
        return 35
    return 10


def _score_budgets(sb, account_ids, budgets, month_start, factors, recommendations):
    if not budgets:
        return 0

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    over_count = 0
    total_budgets = 0

    for budget in budgets:
        category = budget["category"]
        limit_amount = float(budget.get("amount") or 0)
        if limit_amount <= 0:
            continue

        start = budget.get("start_date") or month_start.strftime("%Y-%m-%d")
        end = budget.get("end_date") or today

        if today < start or today > end:
            continue

        total_budgets += 1

        budget_account_ids = [budget["account_id"]] if budget.get("account_id") else account_ids
        spent = _get_category_spending(sb, budget_account_ids, category, start)

        pct = (spent / limit_amount) * 100

        if pct > 100:
            over_count += 1
            overage = spent - limit_amount
            factors.append({
                "factor": "budget_exceeded",
                "severity": "high",
                "detail": f"{category}: ${spent:.2f} spent vs ${limit_amount:.2f} limit ({pct:.0f}%) [{start} to {end}]",
            })
            recommendations.append(
                f"You're ${overage:.2f} over your {category} budget. Try to avoid {category} spending until {end}."
            )
        elif pct > 80:
            factors.append({
                "factor": "budget_warning",
                "severity": "medium",
                "detail": f"{category}: ${spent:.2f} of ${limit_amount:.2f} used ({pct:.0f}%) [{start} to {end}]",
            })

    if total_budgets == 0:
        return 0
    return min(100, (over_count / total_budgets) * 100 + over_count * 15)


def _score_cash_flow(user, balance, monthly_spending, monthly_income, factors, recommendations):
    expected_income = float(user.get("monthly_income") or 0)
    expected_expenses = float(user.get("monthly_expenses") or 0)

    if expected_income <= 0 and monthly_income <= 0:
        return 20  # not enough data

    income_ref = monthly_income if monthly_income > 0 else expected_income

    if income_ref > 0:
        spend_ratio = monthly_spending / income_ref
    else:
        spend_ratio = 2.0 if monthly_spending > 0 else 0

    if spend_ratio > 1.0:
        factors.append({
            "factor": "negative_cash_flow",
            "severity": "critical",
            "detail": f"Spending ${monthly_spending:.2f} vs income ${income_ref:.2f} this month ({spend_ratio:.0%})",
        })
        recommendations.append("You're spending more than you earn this month. Identify and cut non-essential expenses.")
        return 90
    elif spend_ratio > 0.8:
        factors.append({
            "factor": "tight_cash_flow",
            "severity": "medium",
            "detail": f"Spending is {spend_ratio:.0%} of income",
        })
        recommendations.append("Spending is over 80% of income — little room for unexpected expenses.")
        return 55
    elif spend_ratio > 0.6:
        return 25
    return 10


def _score_goals(user, balance, monthly_spending, monthly_income, factors, recommendations):
    savings_goal = float(user.get("savings_goal") or 0)
    current_savings = float(user.get("current_savings") or 0)

    if savings_goal <= 0:
        return 0  # no goal set

    income_ref = monthly_income if monthly_income > 0 else float(user.get("monthly_income") or 0)
    monthly_savings_rate = income_ref - monthly_spending

    remaining = savings_goal - current_savings
    if remaining <= 0:
        return 0  # goal already met

    if monthly_savings_rate <= 0:
        factors.append({
            "factor": "goal_unreachable",
            "severity": "high",
            "detail": f"${remaining:.2f} left to save but monthly savings rate is negative",
        })
        recommendations.append(
            f"At current spending, you can't make progress toward your ${savings_goal:.0f} savings goal. "
            "Reduce expenses to free up savings capacity."
        )
        return 85

    months_to_goal = remaining / monthly_savings_rate
    if months_to_goal > 24:
        factors.append({
            "factor": "goal_delayed",
            "severity": "medium",
            "detail": f"~{months_to_goal:.0f} months to reach savings goal at current rate",
        })
        recommendations.append(
            f"At current savings rate (${monthly_savings_rate:.0f}/mo), "
            f"your goal is ~{months_to_goal:.0f} months away. Increasing savings by even $50/mo helps."
        )
        return 50
    elif months_to_goal > 12:
        return 30
    return 10


# ── Data helpers ────────────────────────────────────────────────────

def _get_transactions_since(sb, account_ids, since_date):
    if not account_ids:
        return []
    result = (
        sb.table("transactions")
        .select("*")
        .in_("account_id", account_ids)
        .gte("transaction_date", since_date)
        .execute()
    )
    return result.data


def _get_category_spending(sb, account_ids, category, since_date):
    if not account_ids:
        return 0
    result = (
        sb.table("transactions")
        .select("amount")
        .in_("account_id", account_ids)
        .eq("category", category)
        .eq("type", "purchase")
        .gte("transaction_date", since_date)
        .execute()
    )
    return sum(t["amount"] for t in result.data)
