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


def add_nessie_purchase_and_sync(
    nessie_account_id,
    merchant_id,
    description,
    amount,
    date,
):
    """Create a Nessie purchase, then run a full Nessie→Supabase sync for that account's user.

    Resolves the Supabase user via ``accounts.nessie_account_id`` (must already be linked).

    Args:
        nessie_account_id: Nessie account ``_id`` (same value stored in ``accounts.nessie_account_id``).
        merchant_id: Nessie merchant ``_id``.
        description: Purchase description.
        amount: Dollar amount (number).
        date: Purchase date ``YYYY-MM-DD``.

    Returns:
        dict with ``success`` (bool). On failure: ``error`` (str), optionally ``user_id``.
        On success: ``user_id`` and ``sync`` (return value of :func:`sync.sync_user`).
    """
    from nessie import add_transaction
    from sync import sync_user

    if not nessie_account_id:
        return {"success": False, "error": "nessie_account_id is required"}

    sb = get_supabase()
    acc = (
        sb.table("accounts")
        .select("id, user_id")
        .eq("nessie_account_id", str(nessie_account_id))
        .limit(1)
        .execute()
    )
    if not acc.data:
        return {
            "success": False,
            "error": "No Supabase account linked to this Nessie account id.",
        }
    user_id = acc.data[0]["user_id"]

    created = add_transaction(
        str(nessie_account_id),
        merchant_id,
        description,
        amount,
        date,
    )
    if not created:
        return {
            "success": False,
            "error": "Nessie did not create the purchase (check API response / logs).",
            "user_id": user_id,
        }

    summary = sync_user(user_id)
    return {"success": True, "user_id": user_id, "sync": summary}


if __name__ == "__main__":
    result = add_nessie_purchase_and_sync(
        nessie_account_id="69bf074695150878ea0006d3",
        merchant_id="57cf75cea73e494d8675ec4a",
        description="Erwhon Shopping",
        amount=500,
        date="2026-03-22",
    )