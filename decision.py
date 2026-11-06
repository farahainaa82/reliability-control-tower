"""Short-horizon sensor projections and the simulated maintenance decision policy."""

from datetime import timedelta
from statistics import linear_regression

HORIZON_HOURS = 6
MIN_SLOPE = {"vibration_mm_s": 0.2, "temperature_c": 1.0}
OPTIONS = (
    ("Continue monitoring", 1.0, "Next telemetry check in 1 hour", "No field dispatch"),
    ("Schedule a field check", 4.0, "Field check within 4 hours", "Use the planned maintenance round"),
    ("Dispatch a priority inspection", 0.25, "Field inspection within 15 minutes", "Bring forward a technician"),
    ("Escalate to the shift lead", 0.0, "Notify shift lead immediately", "Coordinate urgent field verification"),
)


def project(readings, field, limit):
    """Fit the last three readings and project from the latest observed value."""
    recent = readings[-3:]
    latest = recent[-1]
    values = [row[field] for row in recent]
    projection = {"latest": latest["timestamp"], "value": values[-1], "limit": limit,
                  "slope": None, "hours": None, "crossing": None, "exceeded": values[-1] >= limit}
    if projection["exceeded"] or len(recent) < 3 or not values[0] < values[1] < values[2]:
        return projection

    times = [(row["timestamp"] - latest["timestamp"]).total_seconds() / 3600 for row in recent]
    if not times[0] < times[1] < times[2]:
        return projection
    slope = linear_regression(times, values).slope
    if slope < MIN_SLOPE[field]:
        return projection

    hours = (limit - values[-1]) / slope
    if hours <= HORIZON_HOURS:
        projection.update(slope=slope, hours=hours, crossing=latest["timestamp"] + timedelta(hours=hours))
    return projection


def prescribe(result, signals):
    asset = result["asset"]
    projections = {
        field: project(result["readings"], field, float(asset[limit_field]))
        for field, limit_field, *_ in signals
    }
    projected = [
        (projection["hours"], label, projection["crossing"])
        for field, _, label, *_ in signals
        if (projection := projections[field])["hours"] is not None
    ]
    earliest = min(projected, default=None)
    service_overdue = result["latest"]["timestamp"].date() > result["due_date"]
    observed_limit = any(projection["exceeded"] for projection in projections.values())
    priority = result["priority"]

    if priority == "Critical":
        selected = 3
        reason = "Current evidence meets the critical threshold. Escalate now and verify the condition on site."
    elif earliest:
        hours, label, crossing = earliest
        if hours <= OPTIONS[2][1]:
            selected = 3
        elif hours <= OPTIONS[1][1]:
            selected = 2
        else:
            selected = 1
        reason = (f"{label} may reach its limit at {crossing:%H:%M} site time if the trend continues. "
                  "Choose a field response that can start before then.")
    elif priority == "Watch" or observed_limit or service_overdue:
        selected = 1
        reason = "Use the planned round to check the flagged condition or overdue service."
    else:
        selected = 0
        reason = "Current readings and the short-horizon projection support routine monitoring."

    compared = []
    for index, (label, lead, timing, effort) in enumerate(OPTIONS):
        if index == selected:
            verdict = "Recommended"
        elif priority == "Critical" and index != 3:
            verdict = "Escalation required"
        elif earliest and lead >= earliest[0]:
            verdict = "Too late for projected limit"
        elif index == 0:
            verdict = "Field check warranted"
        else:
            verdict = "Higher response effort"
        compared.append((label, timing, effort, verdict))

    return {
        "projections": projections, "earliest": earliest, "options": compared, "rank": selected,
        "action": OPTIONS[selected][0], "window": OPTIONS[selected][2], "reason": reason,
    }
