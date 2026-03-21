"""Agent Orchestrator

Ties the full pipeline together:
  Sync → Risk Agent → Notification Agent → Messaging Agent

Each step is traced with timestamps and structured data so the
frontend can render the reasoning loop visually.
"""

import time
from datetime import datetime, timezone

from db import get_supabase
from sync import sync_user, sync_all
from agents.risk_agent import assess_risk
from agents.notification_agent import should_alert
from agents.messaging_agent import generate_alert_message


def _ts():
    return datetime.now(timezone.utc).isoformat()


def run_pipeline(user_id):
    """Full agent pipeline for one user.

    Returns the usual data plus a `trace` list that logs
    what each agent saw, decided, and produced.
    """
    sb = get_supabase()
    trace = []

    # ── Step 1: Nessie Sync Agent ───────────────────────────────
    t0 = time.time()
    sync_result = sync_user(user_id)
    dur = int((time.time() - t0) * 1000)

    if "error" in sync_result:
        trace.append({
            "agent": "Nessie Sync Agent",
            "status": "error",
            "timestamp": _ts(),
            "duration_ms": dur,
            "input_summary": f"Sync data for user {user_id[:8]}...",
            "output_summary": sync_result["error"],
            "details": sync_result,
        })
        return {"error": sync_result["error"], "step": "sync", "trace": trace}

    event_types = list({e["event_type"] for e in sync_result.get("events", [])})
    trace.append({
        "agent": "Nessie Sync Agent",
        "status": "success",
        "timestamp": _ts(),
        "duration_ms": dur,
        "input_summary": f"Polling Nessie for accounts & transactions",
        "output_summary": (
            f"Synced {sync_result['accounts_synced']} account(s), "
            f"found {sync_result['new_transactions']} new transaction(s)"
        ),
        "details": {
            "accounts_synced": sync_result["accounts_synced"],
            "new_transactions": sync_result["new_transactions"],
            "events_detected": event_types,
        },
    })

    # ── Step 2: Financial Risk Agent ────────────────────────────
    t0 = time.time()
    risk = assess_risk(user_id)
    dur = int((time.time() - t0) * 1000)

    if "error" in risk:
        trace.append({
            "agent": "Financial Risk Agent",
            "status": "error",
            "timestamp": _ts(),
            "duration_ms": dur,
            "input_summary": "Evaluate financial health",
            "output_summary": risk["error"],
            "details": risk,
        })
        return {"error": risk["error"], "step": "risk_assessment", "trace": trace}

    ctx = risk["context"]
    trace.append({
        "agent": "Financial Risk Agent",
        "status": "success",
        "timestamp": _ts(),
        "duration_ms": dur,
        "input_summary": (
            f"Balance ${ctx.get('total_balance', 0):,.2f}, "
            f"spending ${ctx.get('monthly_spending', 0):,.2f}/mo, "
            f"{ctx.get('num_transactions_this_month', 0)} txns this month"
        ),
        "output_summary": (
            f"Risk score {risk['score']}/100 → {risk['risk_level'].upper()}, "
            f"{len(risk['factors'])} factor(s)"
        ),
        "details": {
            "score": risk["score"],
            "risk_level": risk["risk_level"],
            "factors": risk["factors"],
            "recommendations": risk["recommendations"],
            "context": ctx,
        },
    })

    # Store snapshot
    sb.table("snapshots").insert({
        "user_id": user_id,
        "balance": ctx.get("total_balance"),
        "risk_level": risk["risk_level"],
        "data": {
            "score": risk["score"],
            "factors": risk["factors"],
            "recommendations": risk["recommendations"],
            "context": ctx,
        },
    }).execute()

    # ── Step 3: Notification (Critic) Agent ─────────────────────
    t0 = time.time()
    notification = should_alert(user_id, risk)
    dur = int((time.time() - t0) * 1000)

    decision = "ALERT" if notification["should_alert"] else "SUPPRESS"
    channels_str = ", ".join(notification.get("channels", [])) or "none"
    suppressed = notification.get("suppressed_reasons", [])

    trace.append({
        "agent": "Notification Critic Agent",
        "status": "success",
        "timestamp": _ts(),
        "duration_ms": dur,
        "input_summary": (
            f"Risk level: {risk['risk_level']}, score: {risk['score']}, "
            f"{len(risk['factors'])} factor(s)"
        ),
        "output_summary": (
            f"{decision} — channels: {channels_str}"
            + (f" | suppressed: {'; '.join(suppressed)}" if suppressed else "")
        ),
        "details": {
            "decision": decision,
            "channels": notification.get("channels", []),
            "reason": notification.get("reason", ""),
            "suppressed_reasons": suppressed,
            "priority": notification.get("priority"),
        },
    })

    # ── Step 4: Messaging Agent (LLM) ──────────────────────────
    alert_record = None
    if notification["should_alert"]:
        t0 = time.time()
        messages_generated = []

        for channel in notification["channels"]:
            message = generate_alert_message(risk, channel=channel)
            messages_generated.append({"channel": channel, "message": message})

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

        dur = int((time.time() - t0) * 1000)

        trace.append({
            "agent": "Messaging Agent",
            "agent_type": "llm",
            "model": "gpt-4o-mini",
            "status": "success",
            "timestamp": _ts(),
            "duration_ms": dur,
            "input_summary": f"Risk assessment (score {risk['score']}, {len(risk['factors'])} factors)",
            "output_summary": f"Generated {len(messages_generated)} message(s) for: {channels_str}",
            "details": {
                "messages": messages_generated,
            },
        })

        _mark_events_processed(sb, user_id)
    else:
        trace.append({
            "agent": "Messaging Agent",
            "agent_type": "llm",
            "model": "gpt-4o-mini",
            "status": "skipped",
            "timestamp": _ts(),
            "duration_ms": 0,
            "input_summary": "No alert warranted",
            "output_summary": "Skipped — critic agent suppressed notification",
            "details": {},
        })

    return {
        "sync": sync_result,
        "risk": risk,
        "notification": notification,
        "alert": alert_record,
        "trace": trace,
    }


def run_pipeline_all():
    sb = get_supabase()
    users = sb.table("users").select("id").execute()
    return [run_pipeline(u["id"]) for u in users.data]


def assess_only(user_id):
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
    return {"risk": risk, "notification": notification}


def _mark_events_processed(sb, user_id):
    unprocessed = (
        sb.table("events")
        .select("id")
        .eq("user_id", user_id)
        .eq("processed", False)
        .execute()
    )
    for evt in unprocessed.data:
        sb.table("events").update({"processed": True}).eq("id", evt["id"]).execute()
