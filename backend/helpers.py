from datetime import datetime, timezone

from db import get_supabase


def _parse_ymd(s):
    if not s:
        return None
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def _account_ids_for_user(sb, user_id):
    accounts = sb.table("accounts").select("id").eq("user_id", user_id).execute()
    return [a["id"] for a in (accounts.data or [])]


def sum_category_spend(sb, account_ids, category, start_date, end_date, budget_account_id=None):
    """Sum purchase amounts for category in date range (inclusive)."""
    if not account_ids or not category:
        return 0.0
    ids = list(account_ids)
    if budget_account_id and budget_account_id in ids:
        ids = [budget_account_id]
    elif budget_account_id:
        return 0.0

    result = (
        sb.table("transactions")
        .select("amount")
        .in_("account_id", ids)
        .eq("type", "purchase")
        .eq("category", category)
        .gte("transaction_date", start_date[:10])
        .lte("transaction_date", end_date[:10])
        .execute()
    )
    return sum(float(t.get("amount") or 0) for t in (result.data or []))


def get_user_budgets(user_id):
    """Return all budgets for a user with their full data.

    Returns a list of dicts, each containing:
        id, user_id, account_id, category, amount, start_date, end_date, created_at
    Returns an empty list if the user has no budgets.
    """
    result = (
        get_supabase()
        .table("budgets")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return result.data or []


def get_active_budgets_usage(user_id):
    """Budgets whose period includes today (UTC), with spent vs limit."""
    sb = get_supabase()
    today = datetime.now(timezone.utc).date()
    budgets = get_user_budgets(user_id)
    account_ids = _account_ids_for_user(sb, user_id)
    active = []

    for b in budgets:
        d0 = _parse_ymd(b.get("start_date"))
        d1 = _parse_ymd(b.get("end_date"))
        if not d0 or not d1 or d1 < d0:
            continue
        if not (d0 <= today <= d1):
            continue

        cat = (b.get("category") or "").strip()
        if not cat:
            continue

        start_s = str(b.get("start_date"))[:10]
        end_s = str(b.get("end_date"))[:10]
        limit_amt = float(b.get("amount") or 0)
        spent = sum_category_spend(sb, account_ids, cat, start_s, end_s, b.get("account_id"))

        active.append({
            "id": b.get("id"),
            "category": cat,
            "limit": limit_amt,
            "spent": round(spent, 2),
            "remaining": round(max(0.0, limit_amt - spent), 2),
            "pct_used": round(spent / limit_amt, 4) if limit_amt > 0 else None,
            "start_date": start_s,
            "end_date": end_s,
            "is_over": spent > limit_amt if limit_amt > 0 else False,
        })

    return {"active": active, "count": len(active)}


def get_user_budgets_by_nessie_account(nessie_account_id):
    """Resolve a Nessie account id to Supabase ``accounts.user_id``, then load budgets.

    Args:
        nessie_account_id: Value stored in ``accounts.nessie_account_id`` (Nessie API id).

    Returns:
        Same list of budget dicts as :func:`get_user_budgets`. Empty list if the
        Nessie id is missing, no row matches, or ``user_id`` is absent.
    """
    if not nessie_account_id:
        return []
    result = (
        get_supabase()
        .table("accounts")
        .select("user_id")
        .eq("nessie_account_id", str(nessie_account_id))
        .limit(1)
        .execute()
    )
    if not result.data:
        return []
    user_id = result.data[0].get("user_id")
    if not user_id:
        return []
    return get_user_budgets(user_id)


def get_budget_by_id(budget_id, user_id=None):
    """Return one budget row by its primary key ``id``.

    Args:
        budget_id: UUID (or str) of the ``budgets.id`` column.
        user_id: If set, only return the row when it belongs to this user.

    Returns:
        A dict with the full budget row, or ``None`` if not found.
    """
    q = get_supabase().table("budgets").select("*").eq("id", budget_id).limit(1)
    if user_id is not None:
        q = q.eq("user_id", user_id)
    result = q.execute()
    if not result.data:
        return None
    return result.data[0]


def get_transaction_history(user_id, limit=20):
    """Return recent transactions for a user across all their accounts.

    Returns a list of dicts with: amount, type, description, transaction_date.
    Sorted by date descending (most recent first).
    """
    sb = get_supabase()
    accounts = sb.table("accounts").select("id").eq("user_id", user_id).execute()
    account_ids = [a["id"] for a in (accounts.data or [])]
    if not account_ids:
        return []

    # Use select("*") so we never ask PostgREST for a column that might not exist yet.
    # If you add optional columns (e.g. category), they appear automatically once migrated.
    txns = (
        sb.table("transactions")
        .select("*")
        .in_("account_id", account_ids)
        .order("transaction_date", desc=True)
        .limit(limit)
        .execute()
    )
    return txns.data or []


def create_budget(user_id, category, amount, start_date, end_date, account_id=None):
    """Insert or update a budget for a user.

    Args:
        user_id: The user's Supabase ID.
        category: Budget category (e.g. "dining", "groceries").
        amount: Spending limit for the period.
        start_date: Start date as "YYYY-MM-DD" string.
        end_date: End date as "YYYY-MM-DD" string.
        account_id: Optional account ID to scope the budget to.

    Returns the created/updated budget row as a dict.
    Upserts on (user_id, category) so calling twice with the same
    category updates the existing budget.
    """
    sb = get_supabase()
    row = {
        "user_id": user_id,
        "category": category,
        "amount": amount,
        "start_date": start_date,
        "end_date": end_date,
        "account_id": account_id,
    }
    existing = (
        sb.table("budgets")
        .select("id")
        .eq("user_id", user_id)
        .eq("category", category)
        .limit(1)
        .execute()
    )
    if existing.data:
        bid = existing.data[0]["id"]
        update_payload = {
            "category": category,
            "amount": amount,
            "start_date": start_date,
            "end_date": end_date,
            "account_id": account_id,
        }
        result = sb.table("budgets").update(update_payload).eq("id", bid).execute()
    else:
        result = sb.table("budgets").insert(row).execute()
    return result.data[0] if result.data else None

if __name__ == "__main__":
    import random

    USER_ID = "e502c25b-6306-4944-bc77-728048e44a3f"

    months = [
        ("2024-01-01", "2024-01-31", random.randint(200, 400)),
        ("2024-02-01", "2024-02-29", random.randint(200, 400)),
        ("2024-03-01", "2024-03-31", random.randint(200, 400)),
        ("2024-04-01", "2024-04-30", random.randint(200, 400)),
        ("2024-05-01", "2024-05-31", random.randint(200, 400)),
        ("2024-06-01", "2024-06-30", random.randint(200, 400)),
        ("2024-07-01", "2024-07-31", random.randint(200, 400)),
        ("2024-08-01", "2024-08-31", random.randint(200, 400)),
        ("2024-09-01", "2024-09-30", random.randint(200, 400)),
        ("2024-10-01", "2024-10-31", random.randint(200, 400)),
        ("2024-11-01", "2024-11-30", random.randint(200, 400)),
        ("2024-12-01", "2024-12-31", random.randint(200, 400)),
    ]

    for start, end, amount in months:
        b = create_budget(USER_ID, "food", amount, start, end)
        print(f"  Created: food ${amount} ({start} to {end})")

    print(f"\nDone — inserted {len(months)} food budgets for 2024.")