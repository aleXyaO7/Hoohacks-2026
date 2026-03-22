from db import get_supabase


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

    txns = (
        sb.table("transactions")
        .select("amount, type, description, transaction_date")
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
    row = {
        "user_id": user_id,
        "category": category,
        "amount": amount,
        "start_date": start_date,
        "end_date": end_date,
        "account_id": account_id,
    }
    result = (
        get_supabase()
        .table("budgets")
        .insert(row)
        .execute()
    )
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