"""Fetch latest Garmin activities and save to activities.json."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import Garmin

load_dotenv()

EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 20
TOKEN_STORE = ".garmin_tokens"

KEEP_FIELDS = [
    "activityId",
    "activityName",
    "activityType",
    "startTimeLocal",
    "duration",
    "distance",
    "averageHR",
    "maxHR",
    "averageSpeed",
    "maxSpeed",
    "calories",
    "steps",
    "averageRunningCadenceInStepsPerMinute",
    "averagePower",
    "normPower",
    "elevationGain",
    "elevationLoss",
    "minElevation",
    "maxElevation",
    "trainingEffect",
    "aerobicTrainingEffect",
    "anaerobicTrainingEffect",
    "vo2MaxValue",
    "lactateThresholdBpm",
    "avgStrideLength",
    "avgVerticalOscillation",
    "avgGroundContactTime",
    "avgVerticalRatio",
    "sportType",
    "locationName",
    "lapCount",
    "avgPower",
    "deviceId",
]


def slim(activity: dict) -> dict:
    """Keep only the fields we care about, flatten activityType."""
    result = {k: activity[k] for k in KEEP_FIELDS if k in activity}
    if "activityType" in activity:
        result["activityType"] = activity["activityType"].get("typeKey", "unknown")
    return result


def main():
    if not EMAIL or not PASSWORD:
        sys.exit("Set GARMIN_EMAIL and GARMIN_PASSWORD in .env")

    print(f"Logging in as {EMAIL}...")
    client = Garmin(EMAIL, PASSWORD)

    # login() handles both loading from and saving to the token store
    client.login(TOKEN_STORE)
    print("Logged in.")

    print(f"Fetching {LIMIT} activities...")
    raw = client.get_activities(0, LIMIT)
    activities = [slim(a) for a in raw]

    out = {
        "fetched_at": datetime.now().isoformat(),
        "count": len(activities),
        "activities": activities,
    }

    Path("activities.json").write_text(json.dumps(out, indent=2))
    print(f"Saved {len(activities)} activities to activities.json")


if __name__ == "__main__":
    main()
