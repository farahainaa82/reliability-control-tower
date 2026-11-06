"""Deterministic maintenance policy and mock data readers."""

import csv
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

from decision import prescribe

DATA = Path(__file__).resolve().parent / "data"
SIGNALS = (
    ("vibration_mm_s", "vibration_limit", "Vibration", "mm/s RMS", 30, 0.8),
    ("temperature_c", "temperature_limit", "Temperature", "°C", 20, 6.0),
)


def read_csv(filename):
    with (DATA / filename).open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def load_demo(scenario):
    assets = read_csv("assets.csv")
    for asset in assets:
        asset["site"] = asset.get("site") or "Unassigned"
    readings = read_csv("telemetry_baseline.csv")
    if scenario != "baseline":
        batches = defaultdict(list)
        for row in read_csv("telemetry_replay.csv"):
            batches[row["asset_id"]].append(row)
        for batch in batches.values():
            batch.sort(key=lambda row: row["timestamp_ast"])
            readings.extend(batch[:3] if scenario == "early" else batch)

    telemetry = defaultdict(list)
    for row in readings:
        telemetry[row["asset_id"]].append({
            "timestamp": datetime.fromisoformat(row["timestamp_ast"]),
            "vibration_mm_s": float(row["vibration_mm_s"]),
            "temperature_c": float(row["temperature_c"]),
        })
    for records in telemetry.values():
        records.sort(key=lambda row: row["timestamp"])

    maintenance = defaultdict(list)
    for row in read_csv("maintenance.csv"):
        maintenance[row["asset_id"]].append(row)
    return assets, telemetry, maintenance


def assess(asset, readings, history):
    """Summarise evidence and assign a maintenance priority on a 0–100 scale."""
    latest = readings[-1]
    last_service = max(row["date"] for row in history if row["event_type"] == "Preventive service")
    due_date = date.fromisoformat(last_service) + timedelta(days=int(asset["service_interval_days"]))
    days_overdue = max(0, (latest["timestamp"].date() - due_date).days)
    evidence = []
    rising = []
    signal_triggered = False

    for field, limit_field, label, unit, points, trend_trigger in SIGNALS:
        limit = float(asset[limit_field])
        last_three = [row[field] for row in readings[-3:]]
        previous_three = [row[field] for row in readings[-6:-3]]
        exceedances = sum(value > limit for value in last_three)
        if exceedances >= 2:
            signal_triggered = True
            evidence.append((f"{label} above limit", f"{exceedances}/3 readings above {limit:g} {unit}", points))

        change = mean(last_three) - mean(previous_three)
        if round(change, 2) >= trend_trigger:
            rising.append(f"{label.lower()} +{change:.1f} {unit}")

    if rising:
        signal_triggered = True
        evidence.append(("Rapid rise", ", ".join(rising) + " vs prior 3-hour mean", 20))
    if days_overdue:
        evidence.append(("Service overdue", f"{days_overdue} days past scheduled preventive service", 15))
    if signal_triggered and asset["criticality"] == "High":
        evidence.append(("High asset criticality", "Condition alarm on a high-impact asset", 15))

    score = min(100, sum(points for _, _, points in evidence))
    if score >= 70:
        priority, action, window = "Critical", "Prepare a priority inspection", "Within 24 hours of approval"
    elif score >= 35:
        priority, action, window = "Watch", "Verify at the next operating round", "Next operating round"
    else:
        priority, window = "Stable", "Normal schedule"
        action = "Review overdue service" if days_overdue else "Continue routine monitoring"

    return {
        "asset": asset, "readings": readings, "history": history, "latest": latest,
        "last_service": last_service, "due_date": due_date, "evidence": evidence,
        "score": score, "priority": priority, "action": action, "window": window,
    }


def scan(scenario, orders):
    """Rank the fleet and draft or update urgent inspections for planner review."""
    assets, telemetry, maintenance = load_demo(scenario)
    results = []
    created = []
    updated = []
    for asset in assets:
        asset_id = asset["asset_id"]
        result = assess(asset, telemetry[asset_id], maintenance[asset_id])
        decision = prescribe(result, SIGNALS)
        result["decision"] = decision
        results.append(result)
        existing = orders.get(asset_id)
        if decision["rank"] >= 2 and (existing is None or existing["status"] == "Awaiting approval"):
            draft = {
                "id": existing["id"] if existing else f"WO-{1001 + len(orders)}",
                "asset_id": asset_id, "asset_name": asset["name"],
                "owner": asset["owner"], "scope": asset["inspection"],
                "window": decision["window"], "action": decision["action"],
                "decision_reason": decision["reason"], "status": "Awaiting approval",
                "reason": " · ".join(label for label, _, _ in result["evidence"]),
                "score": result["score"],
            }
            orders[asset_id] = draft
            if existing is None:
                created.append(draft["id"])
            elif existing != draft:
                updated.append(draft["id"])

    results.sort(key=lambda item: (-item["score"], item["asset"]["asset_id"]))
    return results, created, updated
