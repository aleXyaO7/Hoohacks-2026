"""Notification (Critic) Agent

Decides whether a risk assessment warrants alerting the user.
Prevents spam by checking recency and deduplication.
All deterministic — no LLM.
"""

from datetime import datetime, timezone, timedelta
from db import get_supabase

# Don't re-alert on the same event type within this window
COOLDOWN_MINUTES = {
    "critical": 15,
    "high": 60,
    "medium": 240,
    "low": 1440,
}

# Minimum risk level that triggers an alert per channel
CHANNEL_THRESHOLDS = {
    "sms": "high",       # only high/critical get texted
    "dashboard": "medium",  # medium+ shows on dashboard
}

SEVERITY_ORDER = ["low", "medium", "high", "critical"]


def should_alert(user_id, risk_assessment):
    """Decide whether to alert the user based on the risk assessment.

    Returns:
        {
            "should_alert": bool,
            "channels": ["sms", "dashboard"],
            "reason": str,
            "priority": "low" | "medium" | "high" | "critical",
            "suppressed_reasons": [ str ... ],
        }
    """
    risk_level = risk_assessment.get("risk_level", "low")
    factors = risk_assessment.get("factors", [])
    score = risk_assessment.get("score", 0)

    result = {
        "should_alert": False,
        "channels": [],
        "reason": "",
        "priority": risk_level,
        "suppressed_reasons": [],
    }

    # Nothing to alert on
    if not factors:
        result["reason"] = "No risk factors detected"
        return result

    # Determine which channels qualify based on risk level
    eligible_channels = []
    for channel, threshold in CHANNEL_THRESHOLDS.items():
        if _severity_gte(risk_level, threshold):
            eligible_channels.append(channel)

    if not eligible_channels:
        result["reason"] = f"Risk level '{risk_level}' below all channel thresholds"
        return result

    # Check cooldown — have we alerted this user recently?
    sb = get_supabase()
    cooldown_mins = COOLDOWN_MINUTES.get(risk_level, 60)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(minutes=cooldown_mins)
    ).isoformat()

    recent_alerts = (
        sb.table("alerts")
        .select("risk_level, channel, sent_at")
        .eq("user_id", user_id)
        .gte("sent_at", cutoff)
        .order("sent_at", desc=True)
        .execute()
    )

    # Filter out channels that already have a recent alert at same or higher severity
    final_channels = []
    for channel in eligible_channels:
        already_sent = any(
            a["channel"] == channel and _severity_gte(a["risk_level"], risk_level)
            for a in recent_alerts.data
        )
        if already_sent:
            result["suppressed_reasons"].append(
                f"{channel}: already alerted at {risk_level} level within {cooldown_mins}min"
            )
        else:
            final_channels.append(channel)

    if not final_channels:
        result["reason"] = "All channels suppressed by cooldown"
        return result

    # Check actionability — at least one factor should have a recommendation
    recommendations = risk_assessment.get("recommendations", [])
    if not recommendations:
        result["suppressed_reasons"].append("No actionable recommendations")
        result["reason"] = "Risk detected but no actionable advice to give"
        return result

    # We're alerting
    max_severity = max(
        (f["severity"] for f in factors),
        key=lambda s: SEVERITY_ORDER.index(s) if s in SEVERITY_ORDER else 0,
    )

    result["should_alert"] = True
    result["channels"] = final_channels
    result["priority"] = max_severity
    result["reason"] = f"{len(factors)} risk factor(s) detected, score {score}"

    return result


def _severity_gte(level, threshold):
    """Return True if level >= threshold in severity order."""
    levels = SEVERITY_ORDER
    if level not in levels or threshold not in levels:
        return False
    return levels.index(level) >= levels.index(threshold)
