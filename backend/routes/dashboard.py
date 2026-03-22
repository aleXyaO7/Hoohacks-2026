"""Dashboard refresh: run analytics budget checks + client reloads data."""

from datetime import datetime, timezone

from flask import Blueprint, jsonify

from analytics import check_budget_over, check_budget_warnings
from db import get_supabase
from helpers import _account_ids_for_user, _parse_ymd, get_user_budgets, sum_category_spend

dashboard_bp = Blueprint("dashboard", __name__)


def _active_budget_rows_for_today(user_id):
    """Full budget rows from Supabase whose period includes today (UTC)."""
    today = datetime.now(timezone.utc).date()
    rows = []
    for b in get_user_budgets(user_id):
        d0 = _parse_ymd(b.get("start_date"))
        d1 = _parse_ymd(b.get("end_date"))
        if not d0 or not d1 or d1 < d0:
            continue
        if not (d0 <= today <= d1):
            continue
        if not b.get("id"):
            continue
        rows.append(b)
    return rows


def _nessie_account_id_for_budget(sb, user_id, budget_account_id):
    """Nessie account id for this budget's scope, or the user's first linked account."""
    if budget_account_id:
        r = (
            sb.table("accounts")
            .select("nessie_account_id")
            .eq("id", budget_account_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    else:
        r = (
            sb.table("accounts")
            .select("nessie_account_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    if not r.data:
        return None
    return r.data[0].get("nessie_account_id")


@dashboard_bp.route("/api/users/<user_id>/dashboard/refresh", methods=["POST"])
def dashboard_refresh(user_id):
    """Run ``check_budget_over`` and ``check_budget_warnings`` for each active budget.

    Does not modify ``analytics.py``; imports and calls it as-is.
    """
    sb = get_supabase()
    results = []

    for b in _active_budget_rows_for_today(user_id):
        budget_id = str(b["id"])
        category = (b.get("category") or "").strip() or "?"
        nessie_aid = _nessie_account_id_for_budget(sb, user_id, b.get("account_id"))

        entry = {
            "budget_id": budget_id,
            "category": category,
            "check_budget_over": None,
            "check_budget_warnings": None,
            "error": None,
        }

        if not nessie_aid:
            entry["error"] = "No Nessie-linked account for this budget."
            results.append(entry)
            continue

        try:
            entry["check_budget_over"] = bool(
                check_budget_over(nessie_aid, budget_id)
            )
        except Exception as e:
            entry["error"] = f"check_budget_over: {e}"
            results.append(entry)
            continue

        try:
            entry["check_budget_warnings"] = bool(
                check_budget_warnings(nessie_aid, budget_id)
            )
        except Exception as e:
            entry["error"] = (
                (entry["error"] or "")
                + ("; " if entry["error"] else "")
                + f"check_budget_warnings: {e}"
            )

        # WhatsApp alerts via chatbot.send_over_budget_alert (Twilio + OpenAI)
        user_phone = None
        try:
            ur = (
                sb.table("users")
                .select("phone")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if ur.data:
                user_phone = (ur.data[0].get("phone") or "").strip() or None
        except Exception:
            pass

        if user_phone and entry.get("error") is None:
            account_ids = _account_ids_for_user(sb, user_id)
            start_s = str(b.get("start_date") or "")[:10]
            end_s = str(b.get("end_date") or "")[:10]
            try:
                spent = float(
                    sum_category_spend(
                        sb,
                        account_ids,
                        category,
                        start_s,
                        end_s,
                        b.get("account_id"),
                    )
                )
            except Exception:
                spent = 0.0
            limit_amt = float(b.get("amount") or 0)

            try:
                from chatbot import send_over_budget_alert

                if entry.get("check_budget_over"):
                    send_over_budget_alert(
                        user_phone,
                        f"{category} spending",
                        spent,
                        limit_amt,
                        category,
                        alert_kind="over",
                    )
                    entry["alert_sent"] = "over_budget"
                elif entry.get("check_budget_warnings"):
                    send_over_budget_alert(
                        user_phone,
                        f"{category} budget pace",
                        spent,
                        limit_amt,
                        category,
                        alert_kind="warning",
                    )
                    entry["alert_sent"] = "pace_warning"
            except Exception as alert_exc:
                entry["alert_error"] = str(alert_exc)
        elif not user_phone and (
            entry.get("check_budget_over") or entry.get("check_budget_warnings")
        ):
            entry["alert_skipped"] = "no_phone_on_user"

        results.append(entry)

    return jsonify({"budget_analytics": results, "count": len(results)})
