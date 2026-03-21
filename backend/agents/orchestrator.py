"""Agent Orchestrator

Ties the full pipeline together:
  Sync → Risk Agent → Notification Agent → Store alert + snapshot

Can be triggered per-user or for all users.
"""

from db import get_supabase
from sync import sync_user, sync_all
from agents.risk_agent import assess_risk
from agents.notification_agent import should_alert
from agents.messaging_agent import generate_alert_message


def run_pipeline(user_id):
    """Full agent pipeline for one user.

    1. Sync Nessie data
    2. Assess financial risk
    3. Decide whether to alert
    4. Store snapshot + alert (if warranted)

    Returns a combined result with sync summary, risk assessment,
    notification decision, and any alert that was created.
    """
    sb = get_supabase()

    # Step 1: Sync
    sync_result = sync_user(user_id)
    if "error" in sync_result:
        return {"error": sync_result["error"], "step": "sync"}

    # Step 2: Risk assessment
    risk = assess_risk(user_id)
    if "error" in risk:
        return {"error": risk["error"], "step": "risk_assessment"}

    # Step 3: Store snapshot
    snapshot_row = {
        "user_id": user_id,
        "balance": risk["context"].get("total_balance"),
        "risk_level": risk["risk_level"],
        "data": {
            "score": risk["score"],
            "factors": risk["factors"],
            "recommendations": risk["recommendations"],
            "context": risk["context"],
        },
    }
    sb.table("snapshots").insert(snapshot_row).execute()

    # Step 4: Notification decision
    notification = should_alert(user_id, risk)

    alert_record = None
    if notification["should_alert"]:
        for channel in notification["channels"]:
            message = generate_alert_message(risk, channel=channel)
            alert_row = {
                "user_id": user_id,
                "channel": channel,
                "message": message,
                "risk_level": risk["risk_level"],
                "reasoning": {
                    "score": risk["score"],
                    "factors": risk["factors"],
                    "notification_reason": notification["reason"],
                },
            }
            result = sb.table("alerts").insert(alert_row).execute()
            if result.data:
                alert_record = result.data[0]

        # Mark related unprocessed events as processed
        _mark_events_processed(sb, user_id)

    return {
        "sync": sync_result,
        "risk": risk,
        "notification": notification,
        "alert": alert_record,
    }


def run_pipeline_all():
    """Run the full pipeline for every user."""
    sb = get_supabase()
    users = sb.table("users").select("id").execute()
    results = []
    for u in users.data:
        results.append(run_pipeline(u["id"]))
    return results


def assess_only(user_id):
    """Run just the risk assessment without syncing (useful for the dashboard)."""
    risk = assess_risk(user_id)
    if "error" in risk:
        return risk

    sb = get_supabase()
    sb.table("snapshots").insert({
        "user_id": user_id,
        "balance": risk["context"].get("total_balance"),
        "risk_level": risk["risk_level"],
        "data": {
            "score": risk["score"],
            "factors": risk["factors"],
            "recommendations": risk["recommendations"],
            "context": risk["context"],
        },
    }).execute()

    notification = should_alert(user_id, risk)

    return {
        "risk": risk,
        "notification": notification,
    }


# ── Helpers ─────────────────────────────────────────────────────────

def _mark_events_processed(sb, user_id):
    """Mark all unprocessed events for this user as processed."""
    unprocessed = (
        sb.table("events")
        .select("id")
        .eq("user_id", user_id)
        .eq("processed", False)
        .execute()
    )
    for evt in unprocessed.data:
        sb.table("events").update({"processed": True}).eq("id", evt["id"]).execute()
