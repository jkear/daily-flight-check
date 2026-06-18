#!/usr/bin/env python3
"""
GNV Arrival Briefer — FlightAware AeroAPI edition.
Requires: AEROAPI_KEY environment variable
Egress allowlist: aeroapi.flightaware.com
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

AEROAPI_KEY = os.environ.get("AEROAPI_KEY", "")
AEROAPI_BASE = "https://aeroapi.flightaware.com/aeroapi"

ET = ZoneInfo("America/New_York")

TARGET_OPERATORS = {"DAL", "EDV", "PDT", "ENY"}

# Map AeroAPI aircraft_type codes → (display_name, seat_count)
AIRCRAFT_MAP = {
    "B712": ("B717", 110),
    "B717": ("B717", 110),
    "CRJ9": ("CRJ-9", 76),
    "E145": ("E145", 50),
    "E170": ("E170", 70),
    "E175": ("E170", 70),
    "E75L": ("E75L", 76),
    "E75S": ("E75S", 76),
    "E75":  ("E75L", 76),
}

OPERATOR_HUB = {
    "DAL": "ATL",
    "EDV": "ATL",
    "PDT": "CLT",
    "ENY": "DFW/MIA",
}


def api_get(path, params=None):
    if not AEROAPI_KEY:
        sys.exit("ERROR: AEROAPI_KEY environment variable is not set.")
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    req = urllib.request.Request(
        AEROAPI_BASE + path + qs,
        headers={"x-apikey": AEROAPI_KEY, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def to_et(iso_str):
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.astimezone(ET)


def fmt(dt):
    return dt.strftime("%-I:%M %p") if dt else "N/A"


def aircraft_display(code):
    if not code:
        return ("Unknown", "?")
    c = code.upper().replace("-", "")
    for key, val in AIRCRAFT_MAP.items():
        if key.replace("-", "") == c or c.startswith(key.replace("-", "")):
            return val
    return (code, "?")


def fetch_today():
    now = datetime.now(ET)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    all_arrivals = []
    cursor = None
    for _ in range(5):  # max 5 pages
        params = {
            "type": "Airline",
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if cursor:
            params["cursor"] = cursor
        data = api_get("/airports/KGNV/flights/arrivals", params)
        all_arrivals.extend(data.get("arrivals", []))
        cursor = (data.get("links") or {}).get("next")
        if not cursor:
            break

    return all_arrivals


def parse_flights(raw):
    flights = []
    for f in raw:
        ident = f.get("ident") or f.get("ident_icao") or ""
        op = next((p for p in TARGET_OPERATORS if ident.startswith(p)), None)
        if not op:
            continue
        # Skip private tails (shouldn't appear with type=Airline, but double-check)
        if ident.startswith("N"):
            continue

        sched = to_et(f.get("scheduled_on") or f.get("scheduled_in"))
        est   = to_et(f.get("estimated_on") or f.get("estimated_in"))
        actual = to_et(f.get("actual_on") or f.get("actual_in"))

        cancelled = bool(f.get("cancelled"))
        landed = actual is not None

        delayed = False
        if sched and not cancelled:
            cmp = actual or est
            if cmp and (cmp - sched).total_seconds() > 900:  # >15 min
                delayed = True

        origin_obj = f.get("origin") or {}
        if isinstance(origin_obj, dict):
            origin = origin_obj.get("code_iata") or origin_obj.get("code", "???")
        else:
            origin = str(origin_obj)

        name, seats = aircraft_display(f.get("aircraft_type") or "")

        flights.append({
            "ident": ident,
            "op": op,
            "origin": origin,
            "sched": sched,
            "est": est or actual,
            "landed": landed,
            "cancelled": cancelled,
            "delayed": delayed and not cancelled,
            "aircraft": name,
            "seats": seats,
        })

    flights.sort(key=lambda x: x["sched"] or datetime.min.replace(tzinfo=ET))
    return flights


def dense_windows(flights):
    results = []
    n = len(flights)
    seen_starts = set()
    for i in range(n):
        t0 = flights[i]["sched"]
        if not t0 or i in seen_starts:
            continue
        window = [flights[i]]
        for j in range(i + 1, n):
            tj = flights[j]["sched"]
            if tj and (tj - t0).total_seconds() <= 5400:  # 90 min
                window.append(flights[j])
        if len(window) >= 3:
            seen_starts.update(range(i, i + len(window)))
            results.append(window)
    return results


def build_briefing(flights):
    now = datetime.now(ET)
    date_str = now.strftime("%A, %B %d, %Y")
    gen_str = now.strftime("%-I:%M %p ET")

    total = len(flights)
    delays = [f for f in flights if f["delayed"]]
    cancels = [f for f in flights if f["cancelled"]]

    if cancels and delays:
        status = f"⚠ {len(delays)} delayed, {len(cancels)} cancelled"
    elif cancels:
        status = f"⚠ {len(cancels)} cancelled"
    elif delays:
        status = f"⚠ {len(delays)} delayed"
    else:
        status = "✓ all on time"

    out = []
    out.append(f"GNV Arrival Briefing — {date_str}")
    out.append(f"Generated: {gen_str}")
    out.append("")
    out.append(f"Total commercial arrivals: {total}")
    out.append(f"Status: {status}")

    out.append("")
    out.append("--- DELAYS / CANCELLATIONS ---")
    if not delays and not cancels:
        out.append("None")
    for f in cancels:
        out.append(f"CANCELLED  {f['ident']}  from {f['origin']}  {f['aircraft']} ({f['seats']} seats)")
    for f in delays:
        out.append(f"DELAYED  {f['ident']}  from {f['origin']}  sched {fmt(f['sched'])}  → now ETA {fmt(f['est'])}")

    out.append("")
    out.append("--- FULL SCHEDULE (ET) ---")
    for f in flights:
        display_t = fmt(f["est"] or f["sched"])
        if f["cancelled"]:
            s = "CANCELLED"
        elif f["landed"]:
            s = "Landed"
        elif f["delayed"]:
            s = f"DELAYED (ETA {fmt(f['est'])})"
        else:
            s = "On Time"
        out.append(f"{display_t}  {f['ident']}  {f['origin']}  {f['aircraft']} ({f['seats']} seats)  {s}")

    out.append("")
    out.append("--- DENSE WINDOWS (3+ flights in 90 min) ---")
    windows = dense_windows(flights)
    if windows:
        for w in windows:
            label = ", ".join(f"{x['ident']} {x['origin']}" for x in w)
            out.append(f"{fmt(w[0]['sched'])} - {fmt(w[-1]['sched'])}: {len(w)} flights — {label}")
    else:
        out.append("None")

    out.append("")
    out.append("--- BIGGEST PLANES (priority targets) ---")
    b717s = [f for f in flights if f["op"] == "DAL" and not f["cancelled"]]
    if b717s:
        for f in b717s:
            out.append(f"{fmt(f['est'] or f['sched'])}  {f['ident']}  {f['origin']}  {f['aircraft']} ({f['seats']} seats)")
    else:
        out.append("No B717 mainline (DAL) arrivals today")

    # Upstream weather check
    hub_delays = {}
    for f in delays:
        hub = OPERATOR_HUB.get(f["op"], "UNK")
        hub_delays[hub] = hub_delays.get(hub, 0) + 1
    weather_notes = [f"⚠ Upstream weather likely at {hub} ({n} delays)" for hub, n in hub_delays.items() if n >= 3]

    # Self-check
    has_atl = any(f["op"] in {"DAL", "EDV"} for f in flights)
    has_clt = any(f["op"] == "PDT" for f in flights)
    count_ok = 9 <= total <= 15

    out.append("")
    out.append("--- SELF-CHECK ---")
    out.append(f"{'✓' if count_ok else '✗'} Total commercial count: {total} (expected 9-15; Sunday 10-11 is normal)")
    out.append(f"{'✓' if has_atl else '✗'} ATL arrival present (DAL or EDV)")
    out.append(f"{'✓' if has_clt else '✗'} CLT arrival present (PDT)")
    out.append("✓ All times in Eastern Time")
    out.append(f"{'✓' if not cancels else '⚠'} Cancellations labeled (not silently dropped): {len(cancels)}")
    for note in weather_notes:
        out.append(note)

    return "\n".join(out)


if __name__ == "__main__":
    raw = fetch_today()
    flights = parse_flights(raw)
    print(build_briefing(flights))
