"""Fetch Garmin activities and save to activities.json.

Usage:
  python fetch_activities.py          # all activities (default)
  python fetch_activities.py 500      # last N activities
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import Garmin

load_dotenv(Path(__file__).parent / ".env")

EMAIL    = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")
TOKEN_STORE = str(Path(__file__).parent / ".garmin_tokens")
BATCH = 100  # max safe page size

KEEP_FIELDS = [
    "activityId", "activityName", "activityType", "startTimeLocal",
    "duration", "distance", "averageHR", "maxHR", "averageSpeed", "maxSpeed",
    "calories", "steps", "averageRunningCadenceInStepsPerMinute",
    "averagePower", "normPower", "elevationGain", "elevationLoss",
    "minElevation", "maxElevation", "trainingEffect",
    "aerobicTrainingEffect", "anaerobicTrainingEffect",
    "vo2MaxValue", "lactateThresholdBpm", "avgStrideLength",
    "avgVerticalOscillation", "avgGroundContactTime", "avgVerticalRatio",
    "sportType", "locationName", "lapCount", "avgPower", "deviceId",
]


def slim(activity: dict) -> dict:
    result = {k: activity[k] for k in KEEP_FIELDS if k in activity}
    if "activityType" in activity:
        result["activityType"] = activity["activityType"].get("typeKey", "unknown")
    return result


def fetch_all(client) -> list:
    """Paginate through every activity on the account."""
    activities = []
    start = 0
    while True:
        batch = client.get_activities(start, BATCH)
        if not batch:
            break
        activities.extend(batch)
        oldest = batch[-1]["startTimeLocal"][:10]
        print(f"  Fetched {len(activities):4d} so far … oldest: {oldest}", end="\r")
        if len(batch) < BATCH:
            break
        start += BATCH
    print()
    return activities


def fetch_n(client, n: int) -> list:
    """Fetch the most recent N activities, paging in batches."""
    activities = []
    start = 0
    while len(activities) < n:
        want = min(BATCH, n - len(activities))
        batch = client.get_activities(start, want)
        if not batch:
            break
        activities.extend(batch)
        if len(batch) < want:
            break
        start += len(batch)
    return activities


def main():
    if not EMAIL or not PASSWORD:
        sys.exit("Set GARMIN_EMAIL and GARMIN_PASSWORD in .env")

    limit_arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    print(f"Logging in as {EMAIL}...")
    client = Garmin(EMAIL, PASSWORD)
    client.login(TOKEN_STORE)
    print("Logged in.")

    if limit_arg == "all":
        print("Fetching all activities (paginating)…")
        raw = fetch_all(client)
    else:
        n = int(limit_arg)
        print(f"Fetching last {n} activities…")
        raw = fetch_n(client, n)

    fetched = [slim(a) for a in raw]

    out_path = Path(__file__).parent / "activities.json"

    # Load existing data and merge — new fetched entries win on conflict
    existing: dict = {}
    if out_path.exists():
        try:
            old = json.loads(out_path.read_text())
            existing = {a["activityId"]: a for a in old.get("activities", [])}
        except Exception:
            pass

    for a in fetched:
        existing[a["activityId"]] = a

    merged = sorted(existing.values(), key=lambda x: x.get("startTimeLocal", ""), reverse=True)

    out = {
        "fetched_at": datetime.now().isoformat(),
        "count": len(merged),
        "activities": merged,
    }

    out_path.write_text(json.dumps(out, indent=2))
    print(f"Saved {len(merged)} activities → activities.json ({len(fetched)} new/updated)")


if __name__ == "__main__":
    main()
