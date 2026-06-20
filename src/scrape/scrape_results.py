"""
Phase 0 — pull championship Olympic-distance results via the official triathlon.org REST API.
Docs: https://developers.triathlon.org/docs/getting-started-with-events-api

BEFORE RUNNING:
  1. Register for a free API key: https://apps-api.triathlon.org/register
  2. Set it in config.yaml (scrape.api_key) OR export TRIATHLON_API_KEY=<key>
  3. python src/scrape/scrape_results.py

Writes one JSON file per program (Elite Men / Elite Women) to data/raw/.
Then run build_manifest.py to generate the coverage CSV.
"""
from __future__ import annotations
import json
import os
import sys
import time
import pathlib
import datetime as dt

import requests
import yaml

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
RAW = ROOT / CFG["paths"]["raw"]
RAW.mkdir(parents=True, exist_ok=True)

API_BASE = CFG["scrape"]["api_base"]
API_KEY = os.environ.get("TRIATHLON_API_KEY") or CFG["scrape"].get("api_key", "")
DELAY = CFG["scrape"]["request_delay_seconds"]
PER_PAGE = CFG["scrape"].get("per_page", 100)

START_YEAR = CFG["study"]["start_year"]
END_YEAR = CFG["study"]["end_year"]

if not API_KEY:
    sys.exit(
        "ERROR: No API key found.\n"
        "  Register at https://apps-api.triathlon.org/register then either:\n"
        "  • set scrape.api_key in config.yaml, or\n"
        "  • export TRIATHLON_API_KEY=<your_key>"
    )

SESSION = requests.Session()
SESSION.headers.update({"apikey": API_KEY})


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def api_get(path: str, params: dict | None = None) -> dict:
    """GET from the triathlon API with polite delay and error handling."""
    url = f"{API_BASE}{path}"
    resp = SESSION.get(url, params=params, timeout=30)
    time.sleep(DELAY)
    if resp.status_code == 401:
        sys.exit("ERROR: API key rejected (401). Check scrape.api_key in config.yaml.")
    resp.raise_for_status()
    return resp.json()


def paginate(path: str, params: dict | None = None) -> list[dict]:
    """Fetch all pages of a paginated endpoint."""
    params = dict(params or {})
    params["per_page"] = PER_PAGE
    page, results = 1, []
    while True:
        params["page"] = page
        data = api_get(path, params)
        # API wraps results in {"data": [...], "total_results": N}
        batch = data.get("data", [])
        results.extend(batch)
        total = data.get("total_results", len(batch))
        if len(results) >= total or not batch:
            break
        page += 1
    return results


# ---------------------------------------------------------------------------
# Step 1 — category IDs for our three championship tiers
# ---------------------------------------------------------------------------
# Known-stable category IDs from the API.
# The script calls /events/categories at startup and prints the full list
# so you can verify or update these if World Triathlon restructures categories.
TIER_CATEGORY_IDS: dict[str, list[int]] = {
    # Annual WTCS/WTS Grand Final race (cat 624 = "World Championship Finals")
    "world_championship": [624],
    # Continental Championships — European, Pan-American, African, Asian-Pacific, Oceania
    # (cat 340 = "Continental Championships")
    "continental":        [340],
    # Olympic Games, Commonwealth Games, Asian Games, etc.
    # (cat 343 = "Major Games") — manifest will filter to Olympics only by event name
    "olympic_games":      [343],
}

ELITE_PROGRAM_KEYWORDS = {"elite men", "elite women"}


def discover_categories() -> None:
    """Print all available categories to help verify / update TIER_CATEGORY_IDS."""
    cats = api_get("/events/categories").get("data", [])
    print("\n--- Available event categories ---")
    for c in cats:
        print(f"  {c.get('cat_id'):>6}  {c.get('cat_name')}")
    print("----------------------------------\n")


# ---------------------------------------------------------------------------
# Step 2 — find all in-scope events
# ---------------------------------------------------------------------------
def find_events() -> list[dict]:
    """Return all championship events in the study window across enabled tiers."""
    tiers_cfg = CFG.get("tiers", {})
    start_date = f"{START_YEAR}-01-01"
    end_date   = f"{END_YEAR}-12-31"
    collected: dict[int, dict] = {}  # event_id → event

    for tier, cat_ids in TIER_CATEGORY_IDS.items():
        if not tiers_cfg.get(tier, True):
            continue
        cat_str = "|".join(str(c) for c in cat_ids)
        events = paginate(
            "/events",
            {"category_id": cat_str, "start_date": start_date, "end_date": end_date},
        )
        for ev in events:
            eid = ev.get("event_id")
            if eid and eid not in collected:
                ev["_tier"] = tier
                collected[eid] = ev
        print(f"  Tier '{tier}': found {len(events)} events (category_ids={cat_ids})")

    return list(collected.values())


# ---------------------------------------------------------------------------
# Step 3 — for each event, find Elite Men / Women programs
# ---------------------------------------------------------------------------
def get_elite_programs(event_id: int) -> list[dict]:
    """Return Elite Men and Elite Women program objects for a given event."""
    data = api_get(f"/events/{event_id}/programs")
    programs = data.get("data", [])
    elite = []
    for p in programs:
        name = (p.get("prog_name") or "").lower()
        if any(kw in name for kw in ELITE_PROGRAM_KEYWORDS):
            elite.append(p)
    return elite


# ---------------------------------------------------------------------------
# Step 4 — pull results for one program
# ---------------------------------------------------------------------------
def get_results(event_id: int, prog_id: int) -> list[dict]:
    """Return the full results array for an event/program."""
    data = api_get(f"/events/{event_id}/programs/{prog_id}/results")
    return data.get("data", [])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print(f"Triathlon API scraper — {dt.datetime.now().isoformat(timespec='seconds')}")
    print(f"Study window: {START_YEAR}–{END_YEAR}")

    # Print the category taxonomy so you can cross-check TIER_CATEGORY_IDS
    discover_categories()

    print("Searching for in-scope championship events …")
    events = find_events()

    # Supplement: fetch specific events not reachable via category filter
    # (Grand Finals that sit in category 351 rather than 624)
    SUPPLEMENTAL_EVENTS: dict[int, str] = {
        117107: "world_championship",   # 2018 ITU Grand Final Gold Coast
        130051: "world_championship",   # 2021 World Triathlon Championship Finals Edmonton
    }
    existing_ids = {e["event_id"] for e in events}
    for eid, tier in SUPPLEMENTAL_EVENTS.items():
        if eid not in existing_ids:
            try:
                ev_data = api_get(f"/events/{eid}").get("data", {})
                if ev_data:
                    ev_data["_tier"] = tier
                    events.append(ev_data)
                    print(f"  Supplemental: {ev_data.get('event_title')} (tier={tier})")
            except Exception as exc:
                print(f"  Supplemental FAIL event={eid}: {exc}")

    print(f"Total unique events found: {len(events)}\n")

    failures: list[dict] = []
    saved = 0

    for ev in events:
        event_id   = ev["event_id"]
        event_name = ev.get("event_title", "")
        event_date = ev.get("event_date", "")
        tier       = ev.get("_tier", "unknown")
        year       = (event_date or "")[:4] or "0000"

        try:
            programs = get_elite_programs(event_id)
        except Exception as exc:
            failures.append({"event_id": event_id, "error": f"programs: {exc}"})
            print(f"  FAIL programs  event={event_id} {event_name}: {exc}")
            continue

        if not programs:
            print(f"  SKIP (no elite programs)  event={event_id} {event_name}")
            continue

        for prog in programs:
            prog_id   = prog["prog_id"]
            prog_name = prog.get("prog_name", "")
            sex       = "women" if "women" in prog_name.lower() else "men"
            stem      = f"{year}_{tier}_{sex}_{event_id}_{prog_id}"
            out_path  = RAW / f"{stem}.json"

            if out_path.exists():
                print(f"  SKIP (exists)  {stem}")
                continue

            try:
                results = get_results(event_id, prog_id)
            except Exception as exc:
                failures.append({"event_id": event_id, "prog_id": prog_id, "error": str(exc)})
                print(f"  FAIL results   {stem}: {exc}")
                continue

            payload = {
                "race_meta": {
                    "race_id":    f"{event_id}_{prog_id}",
                    "event_id":   event_id,
                    "prog_id":    prog_id,
                    "year":       int(year) if year.isdigit() else None,
                    "tier":       tier,
                    "sex":        sex,
                    "event_name": event_name,
                    "prog_name":  prog_name,
                    "date":       event_date,
                    "venue":      ev.get("event_venue"),
                    "lat":        ev.get("event_latitude"),
                    "lon":        ev.get("event_longitude"),
                    "country":    ev.get("event_country"),
                },
                "program_meta": prog,
                "results":      results,
            }
            out_path.write_text(json.dumps(payload, indent=2, default=str))
            print(f"  OK  {stem}  ({len(results)} athletes)")
            saved += 1

    # Summary
    print(f"\nDone. Saved {saved} programs. Failures: {len(failures)}.")
    if failures:
        fail_path = RAW / "_scrape_failures.json"
        fail_path.write_text(json.dumps(failures, indent=2))
        print(f"Failure log → {fail_path}")

    print("Next step: python src/scrape/build_manifest.py")


if __name__ == "__main__":
    main()
