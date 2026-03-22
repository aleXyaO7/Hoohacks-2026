"""Nessie Sync Service

Pulls accounts and transactions from the Nessie API,
compares against what's stored in Supabase, writes new data,
and emits events for the agent pipeline.
"""

from datetime import datetime, timezone
from db import get_supabase
from nessie import query, get_transactions

NESSIE_BASE = "http://api.nessieisreal.com"

# Map Nessie merchant ``category`` strings (and close variants) → our labels
NESSIE_MERCHANT_CATEGORY_MAP = {
    "food": "food",
    "restaurant": "food",
    "groceries": "food",
    "grocery": "food",
    "rent": "rent/housing",
    "housing": "rent/housing",
    "utilities": "rent/housing",
    "utility": "rent/housing",
    "entertainment": "entertainment",
    "misc": "miscellaneous",
    "miscellaneous": "miscellaneous",
    "other": "miscellaneous",
}

# ── Thresholds for event detection ──────────────────────────────────

LARGE_TRANSACTION_THRESHOLD = 100
LOW_BALANCE_THRESHOLD = 200
PAYCHECK_MIN_AMOUNT = 400


# ── Nessie helpers (using query() for endpoints nessie.py doesn't wrap) ──

def fetch_nessie_accounts(nessie_customer_id):
    """GET /customers/{id}/accounts"""
    resp = query(f"{NESSIE_BASE}/customers/{nessie_customer_id}/accounts", {})
    if resp.status_code == 200:
        return resp.json()
    return []


def fetch_nessie_account(nessie_account_id):
    """GET /accounts/{id}"""
    resp = query(f"{NESSIE_BASE}/accounts/{nessie_account_id}", {})
    if resp.status_code == 200:
        return resp.json()
    return None


def fetch_nessie_deposits(nessie_account_id):
    """GET /accounts/{id}/deposits"""
    resp = query(f"{NESSIE_BASE}/accounts/{nessie_account_id}/deposits", {})
    if resp.status_code == 200:
        return resp.json()
    return []


def fetch_nessie_merchant(merchant_id):
    """GET /merchants/{id} — includes ``category`` when present."""
    if not merchant_id:
        return None
    resp = query(f"{NESSIE_BASE}/merchants/{merchant_id}", {})
    if resp.status_code == 200:
        return resp.json()
    return None


def _map_nessie_merchant_category(merchant):
    """Return one of SYNC_CATEGORIES from a Nessie merchant object, or None."""
    if not merchant:
        return None
    raw = (merchant.get("category") or "").strip().lower()
    if not raw:
        return None
    if raw in NESSIE_MERCHANT_CATEGORY_MAP:
        return NESSIE_MERCHANT_CATEGORY_MAP[raw]
    for key, val in NESSIE_MERCHANT_CATEGORY_MAP.items():
        if key in raw or raw in key:
            return val
    return None


def _infer_category_from_description(description, txn_type):
    """Keyword fallback when merchant category is unknown (deposits: mostly misc)."""
    d = (description or "").lower()

    if txn_type == "deposit":
        if any(k in d for k in ("rent", "mortgage", "landlord", "lease", "housing")):
            return "rent/housing"
        return "miscellaneous"

    rent_kw = (
        "rent",
        "mortgage",
        "landlord",
        "apartment",
        "hoa",
        "utilities",
        "utility",
        "electric",
        "water bill",
        "sewer",
        "internet",
        "comcast",
        "fios",
        "verizon",
        "housing",
    )
    if any(k in d for k in rent_kw):
        return "rent/housing"

    ent_kw = (
        "netflix",
        "spotify",
        "hulu",
        "disney",
        "movie",
        "theater",
        "theatre",
        "concert",
        "steam",
        "playstation",
        "xbox",
        "ticketmaster",
        "entertainment",
        "gym",
        "fitness",
    )
    if any(k in d for k in ent_kw):
        return "entertainment"

    food_kw = (
        "grocery",
        "groceries",
        "restaurant",
        "chipotle",
        "starbucks",
        "food",
        "dining",
        "cafe",
        "coffee",
        "pizza",
        "burger",
        "mcdonald",
        "walmart",
        "target",
        "whole foods",
        "trader joe",
        "safeway",
        "kroger",
        "aldi",
        "uber eats",
        "doordash",
        "grubhub",
    )
    if any(k in d for k in food_kw):
        return "food"

    return "miscellaneous"


def _resolve_sync_category(nt, txn_type, merchant_cache):
    """Pick category for a Nessie purchase/deposit row."""
    if txn_type == "purchase":
        mid = nt.get("merchant_id")
        if mid:
            if mid not in merchant_cache:
                merchant_cache[mid] = fetch_nessie_merchant(mid)
            mapped = _map_nessie_merchant_category(merchant_cache[mid])
            if mapped:
                return mapped
    desc = nt.get("description") or ""
    return _infer_category_from_description(desc, txn_type)


# ── Core sync logic ─────────────────────────────────────────────────

def sync_user(user_id):
    """Full sync for one user: accounts, transactions, event detection.

    Returns a summary dict with counts and detected events.
    """
    sb = get_supabase()

    user_result = sb.table("users").select("*").eq("id", user_id).execute()
    if not user_result.data:
        return {"error": "User not found"}
    user = user_result.data[0]
    nessie_cid = user["nessie_customer_id"]

    summary = {
        "user_id": user_id,
        "accounts_synced": 0,
        "new_transactions": 0,
        "events": [],
    }

    # Fetch all Nessie accounts for this customer
    nessie_accounts = fetch_nessie_accounts(nessie_cid)

    for na in nessie_accounts:
        nessie_aid = na["_id"]
        nessie_balance = na.get("balance", 0)

        # ── Upsert account in Supabase ──────────────────────────
        existing = (
            sb.table("accounts")
            .select("*")
            .eq("nessie_account_id", nessie_aid)
            .execute()
        )

        now = datetime.now(timezone.utc).isoformat()

        if existing.data:
            account = existing.data[0]
            old_balance = float(account.get("balance") or 0)
            sb.table("accounts").update({
                "balance": nessie_balance,
                "last_synced_at": now,
            }).eq("id", account["id"]).execute()
        else:
            result = sb.table("accounts").insert({
                "user_id": user_id,
                "nessie_account_id": nessie_aid,
                "type": na.get("type", "Unknown"),
                "balance": nessie_balance,
                "last_synced_at": now,
            }).execute()
            account = result.data[0]
            old_balance = 0

        summary["accounts_synced"] += 1

        # One cache per Nessie account to avoid repeat merchant GETs
        merchant_cache = {}

        # ── Sync purchases ──────────────────────────────────────
        nessie_txns = get_transactions(nessie_aid)
        if isinstance(nessie_txns, list):
            new_purchase_events = _sync_transactions(
                sb,
                user,
                account,
                nessie_txns,
                "purchase",
                nessie_balance,
                merchant_cache,
            )
            summary["new_transactions"] += len(new_purchase_events)
            summary["events"].extend(new_purchase_events)

        # ── Sync deposits ───────────────────────────────────────
        nessie_deps = fetch_nessie_deposits(nessie_aid)
        if isinstance(nessie_deps, list):
            new_deposit_events = _sync_transactions(
                sb,
                user,
                account,
                nessie_deps,
                "deposit",
                nessie_balance,
                merchant_cache,
            )
            summary["new_transactions"] += len(new_deposit_events)
            summary["events"].extend(new_deposit_events)

        # ── Balance-level events ────────────────────────────────
        balance_events = _check_balance_events(
            user, account, old_balance, nessie_balance
        )
        for evt in balance_events:
            sb.table("events").insert({
                "user_id": user_id,
                "event_type": evt["event_type"],
                "payload": evt["payload"],
            }).execute()
            summary["events"].append(evt)

    return summary


def sync_all():
    """Sync every user in the system. Returns list of per-user summaries."""
    sb = get_supabase()
    users = sb.table("users").select("id").execute()
    results = []
    for u in users.data:
        results.append(sync_user(u["id"]))
    return results


# ── Internal helpers ────────────────────────────────────────────────

def _is_duplicate_key_error(exc):
    """True if Postgres/PostgREST rejected the row as a duplicate."""
    msg = str(exc).lower()
    return (
        "duplicate" in msg
        or "unique" in msg
        or "23505" in msg
        or "already exists" in msg
    )


def _sync_transactions(
    sb, user, account, nessie_txns, txn_type, current_balance, merchant_cache=None
):
    """Compare Nessie transactions against Supabase, insert new ones,
    and return a list of detected events for the new transactions.

    Skips duplicates by ``nessie_transaction_id`` (already in DB, repeated in
    the Nessie payload, or rejected by a unique constraint).

    Sets ``category`` on each row (food, rent/housing, entertainment, miscellaneous)
    using the Nessie merchant ``category`` when available, else description keywords.
    """
    if merchant_cache is None:
        merchant_cache = {}
    existing = (
        sb.table("transactions")
        .select("nessie_transaction_id")
        .eq("account_id", account["id"])
        .execute()
    )
    existing_ids = {
        t["nessie_transaction_id"]
        for t in (existing.data or [])
        if t.get("nessie_transaction_id")
    }

    events = []

    for nt in nessie_txns:
        tid = nt.get("_id")
        if not tid or tid in existing_ids:
            continue

        # Map Nessie fields to our schema
        amount = nt.get("amount", 0)
        description = nt.get("description", "")
        date_field = nt.get("purchase_date") or nt.get("transaction_date")

        category = _resolve_sync_category(nt, txn_type, merchant_cache)

        row = {
            "account_id": account["id"],
            "nessie_transaction_id": tid,
            "type": txn_type,
            "amount": amount,
            "description": description,
            "merchant_id": nt.get("merchant_id"),
            "transaction_date": date_field,
            "category": category,
        }
        try:
            sb.table("transactions").insert(row).execute()
        except Exception as e:
            if _is_duplicate_key_error(e):
                continue
            raise

        existing_ids.add(tid)

        # Detect events for this new transaction
        txn_events = _detect_transaction_events(
            user, account, nt, txn_type, current_balance
        )
        for evt in txn_events:
            sb.table("events").insert({
                "user_id": user["id"],
                "event_type": evt["event_type"],
                "payload": evt["payload"],
            }).execute()
            events.append(evt)

    return events


def _detect_transaction_events(user, account, transaction, txn_type, current_balance):
    """Return a list of event dicts triggered by a single new transaction."""
    events = []
    amount = transaction.get("amount", 0)
    description = transaction.get("description", "")

    base_payload = {
        "amount": amount,
        "description": description,
        "merchant_id": transaction.get("merchant_id"),
        "account_id": account["id"],
        "account_type": account.get("type"),
    }

    # Every new transaction is an event
    events.append({
        "event_type": "new_transaction",
        "payload": base_payload,
    })

    # Large transaction
    if amount >= LARGE_TRANSACTION_THRESHOLD:
        events.append({
            "event_type": "large_transaction",
            "payload": {**base_payload, "threshold": LARGE_TRANSACTION_THRESHOLD},
        })

    # Paycheck detection (deposits above threshold)
    if txn_type == "deposit" and amount >= PAYCHECK_MIN_AMOUNT:
        events.append({
            "event_type": "paycheck_received",
            "payload": {**base_payload},
        })

    # Budget check — compare category spending to weekly/monthly limits
    _budget_events = _check_budget(user, account, transaction)
    events.extend(_budget_events)

    return events


def _check_balance_events(user, account, old_balance, new_balance):
    """Detect balance-level events (low balance, big drops)."""
    events = []

    if new_balance < LOW_BALANCE_THRESHOLD and old_balance >= LOW_BALANCE_THRESHOLD:
        events.append({
            "event_type": "low_balance",
            "payload": {
                "balance": new_balance,
                "previous_balance": old_balance,
                "threshold": LOW_BALANCE_THRESHOLD,
                "account_id": account["id"],
            },
        })

    return events


def _check_budget(user, account, transaction):
    """Check if this transaction pushes any budget category over its limit."""
    sb = get_supabase()
    events = []

    # Nessie purchases don't have categories, so we use description as a proxy.
    # In a real system you'd have a categorization layer.
    # For now, skip if no budgets are set.
    budgets = (
        sb.table("budgets")
        .select("*")
        .eq("user_id", user["id"])
        .execute()
    )
    if not budgets.data:
        return events

    # Sum spending per category for this account in the current month
    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    ).strftime("%Y-%m-%d")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for budget in budgets.data:
        category = budget["category"]
        limit_amount = float(budget.get("amount") or 0)
        if limit_amount <= 0:
            continue

        start = budget.get("start_date") or month_start
        end = budget.get("end_date") or today

        if today < start or today > end:
            continue

        target_account = budget.get("account_id") or account["id"]
        spent_result = (
            sb.table("transactions")
            .select("amount")
            .eq("account_id", target_account)
            .eq("category", category)
            .gte("transaction_date", start)
            .execute()
        )
        total_spent = sum(t["amount"] for t in spent_result.data)

        if total_spent > limit_amount:
            events.append({
                "event_type": "budget_exceeded",
                "payload": {
                    "category": category,
                    "spent": total_spent,
                    "limit": limit_amount,
                    "overage": total_spent - limit_amount,
                    "period": f"{start} to {end}",
                },
            })

    return events
