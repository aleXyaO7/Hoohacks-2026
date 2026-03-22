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
