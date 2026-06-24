"""Scrape athlete data from Power of 10 and save to po10_<guid>.json.

Usage:
  python fetch_po10.py <athlete-guid-or-url> [<athlete-guid-or-url> ...]

Examples:
  python fetch_po10.py 86be7de6-6903-4278-b494-710b2756c6fe
  python fetch_po10.py https://www.powerof10.uk/Home/Athlete/86be7de6-...
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "https://www.powerof10.uk/Home/Athlete/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

# Field events store values in cm, not centiseconds
FIELD_EVENTS = {"Shot", "Javelin", "Discus", "Hammer", "LJ", "TJ", "HJ", "PV", "SP"}


def extract_guid(arg: str) -> str:
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", arg)
    if not m:
        sys.exit(f"Could not find a GUID in: {arg}")
    return m.group(0)


def extract_scalar(src: str, varname: str) -> str | None:
    m = re.search(rf"var {re.escape(varname)}\s*=\s*'([^']*)'", src)
    return m.group(1) if m else None


def extract_array(src: str, varname: str) -> list[str]:
    m = re.search(rf"var {re.escape(varname)}\s*=\s*\[([^\]]*)\]", src)
    if not m:
        return []
    items = re.findall(r"'([^']*)'|(-?\d+\.?\d*)", m.group(1))
    return [a or b for a, b in items]


def centisecs_to_str(cs: str) -> str:
    """Convert centiseconds string to mm:ss or h:mm:ss."""
    try:
        total_s = int(cs) // 100
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except (ValueError, TypeError):
        return cs


def cm_to_m(cm: str) -> str:
    try:
        return f"{int(cm) / 100:.2f}m"
    except (ValueError, TypeError):
        return cm


def extract_profile(src: str) -> dict:
    """Pull name, club, age group, rankings from page HTML."""
    profile = {}

    fn = re.search(r'class="name">\s*([^\n<]+)', src)
    ln = re.search(r'class="surname">\s*([^\n<]+)', src)
    if fn and ln:
        profile["name"] = f"{fn.group(1).strip()} {ln.group(1).strip()}"

    club = re.search(r'title="([^"]+AC[^"]*)"', src)
    if club:
        profile["club"] = club.group(1).strip()

    m = re.search(r"V\d{2}", src)
    if m:
        profile["age_group"] = m.group(0)

    # County: appears as a bare <strong> tag containing a county/region name
    # Exclude gender words (Men/Women) that also appear in <strong> tags
    county_m = re.search(r"<strong>(?!Men\b|Women\b)([A-Z][a-zA-Z &]+)</strong>", src)
    if county_m:
        profile["county"] = county_m.group(1).strip()

    # Age-group rank: matches V45M, V45F, U20M, U20W, U17M, U17W etc.
    ag_m = re.search(r"UK ([VU]\d+([MFW]))[^\d]{0,10}(\d[\d,]+)", src)
    if ag_m:
        ag_label = ag_m.group(1)              # e.g. "V45F" or "U20M"
        gender_code = ag_m.group(2)           # M / F / W
        profile["rank_ag_label"] = ag_label
        profile["rank_ag"]       = ag_m.group(3)
        profile["gender"]        = "Women" if gender_code in ("F", "W") else "Men"

    # Fallback gender from "UK Men" / "UK Women" in the carousel
    if not profile.get("gender"):
        if re.search(r"UK Women[^\d]{0,10}\d", src):
            profile["gender"] = "Women"
        elif re.search(r"UK Men[^\d]{0,10}\d", src):
            profile["gender"] = "Men"

    # Gender rank
    gender = profile.get("gender", "")
    if gender:
        gm = re.search(rf"UK {gender}[^\d]{{0,10}}(\d[\d,]+)", src)
        if gm:
            profile["rank_gender"] = gm.group(1)

    # Overall UK rank
    m = re.search(r"UK Overall[^\d]{0,10}(\d[\d,]+)", src)
    if m:
        profile["rank_uk"] = m.group(1)

    # Handicap
    m = re.search(r"Handicap[^\d]*(\d+\.\d)", src)
    if m:
        profile["handicap"] = m.group(1)

    return profile


def scrape_athlete(guid: str) -> dict:
    url = BASE_URL + guid
    print(f"  Fetching {url} …")
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code == 404:
        raise ValueError(f"Athlete not found (404) — check the GUID is correct: {guid}")
    resp.raise_for_status()
    src = resp.text
    if "dataEventName0" not in src:
        raise ValueError("Page loaded but no athlete data found — the GUID may be invalid or the athlete has no recorded results")

    profile = extract_profile(src)
    print(f"  Athlete: {profile.get('name','?')} | {profile.get('club','?')}")

    # How many events are embedded
    n_events = len(re.findall(r"var dataEventName\d+", src))

    events = []
    for i in range(n_events):
        code = extract_scalar(src, f"dataEventCode{i}")
        name = extract_scalar(src, f"dataEventName{i}")
        pb_raw = extract_scalar(src, f"dataPbValue{i}")

        is_field = code in FIELD_EVENTS if code else False
        pb_display = cm_to_m(pb_raw) if is_field else centisecs_to_str(pb_raw) if pb_raw else None

        meetings  = extract_array(src, f"dataRpMeetings{i}")
        dates     = extract_array(src, f"dataRpMeetDates{i}")
        values    = extract_array(src, f"dataRpValues{i}")
        locations = extract_array(src, f"dataRpLocations{i}")
        positions = extract_array(src, f"dataRpPositions{i}")
        age_groups = extract_array(src, f"dataRpAgeGroups{i}")

        results = []
        for j in range(len(dates)):
            raw_perf = values[j] if j < len(values) else None
            results.append({
                "date":     dates[j]      if j < len(dates)      else None,
                "perf_raw": raw_perf,
                "perf":     (cm_to_m(raw_perf) if is_field else centisecs_to_str(raw_perf)) if raw_perf else None,
                "meeting":  meetings[j]   if j < len(meetings)   else None,
                "venue":    locations[j]  if j < len(locations)  else None,
                "position": positions[j]  if j < len(positions)  else None,
                "ag":       age_groups[j] if j < len(age_groups) else None,
            })

        # Sort chronologically
        results.sort(key=lambda r: r["date"] or "")

        events.append({
            "event":    name,
            "code":     code,
            "is_field": is_field,
            "pb_raw":   pb_raw,
            "pb":       pb_display,
            "results":  results,
        })
        print(f"    {name:<15} PB: {pb_display:<10} {len(results)} results")

    return {
        "guid":       guid,
        "url":        url,
        "fetched_at": datetime.now().isoformat(),
        "profile":    profile,
        "events":     events,
    }


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)

    out_dir = Path(__file__).parent
    saved = []

    for arg in args:
        guid = extract_guid(arg)
        print(f"\nScraping {guid} …")
        try:
            data = scrape_athlete(guid)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        out_path = out_dir / f"po10_{guid}.json"
        out_path.write_text(json.dumps(data, indent=2))
        print(f"  Saved → {out_path.name}")
        saved.append(str(out_path.name))

    # Update athletes index
    index_path = out_dir / "po10_athletes.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"athletes": []}
    existing_guids = {a["guid"] for a in index["athletes"]}
    for arg in args:
        guid = extract_guid(arg)
        if guid not in existing_guids:
            data_path = out_dir / f"po10_{guid}.json"
            if data_path.exists():
                d = json.loads(data_path.read_text())
                index["athletes"].append({
                    "guid": guid,
                    "name": d["profile"].get("name", "Unknown"),
                    "club": d["profile"].get("club", ""),
                    "file": f"po10_{guid}.json",
                    "added": datetime.now().isoformat(),
                })
    index_path.write_text(json.dumps(index, indent=2))
    print(f"\nAthletes index updated ({len(index['athletes'])} total).")


if __name__ == "__main__":
    main()
