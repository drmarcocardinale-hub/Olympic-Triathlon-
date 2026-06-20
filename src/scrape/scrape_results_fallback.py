"""
Phase 0 — FALLBACK scraper using Playwright (local Mac only).

Use this if the official API key is not yet available.
The main scraper (scrape_results.py) is preferred once you have a key.

SETUP (run once in your Mac Terminal):
  pip install playwright
  playwright install chromium

RUN:
  python src/scrape/scrape_results_fallback.py

HOW IT WORKS:
  1. Navigates to the events.triathlon.org results listing
  2. Collects championship event URLs + program IDs
  3. Loads each results page (JS-rendered), waits for the table, extracts splits
  4. Saves one JSON per program to data/raw/ (same schema as scrape_results.py)

NOTES:
  - Runs headless by default; set HEADLESS=false to watch it work
  - Skips files that already exist (safe to re-run)
  - Respects a 2-second delay between pages
"""
from __future__ import annotations
import json
import os
import re
import time
import pathlib
import datetime as dt

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
RAW = ROOT / CFG["paths"]["raw"]
RAW.mkdir(parents=True, exist_ok=True)

START_YEAR = CFG["study"]["start_year"]
END_YEAR   = CFG["study"]["end_year"]
DELAY      = CFG["scrape"]["request_delay_seconds"]
HEADLESS   = os.environ.get("HEADLESS", "true").lower() != "false"

EVENTS_BASE = "https://events.triathlon.org"

# ---------------------------------------------------------------------------
# Championship event categories to search (URL filter param values)
# ---------------------------------------------------------------------------
CATEGORY_FILTERS = [
    "World+Championships",
    "Continental+Championships",
    "Olympic+Games",
]

ELITE_KEYWORDS = {"elite men", "elite women"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_split(text: str | None) -> int | None:
    """'0:18:42' or '18:42' → seconds. Returns None if unparseable."""
    if not text:
        return None
    text = text.strip()
    if not text or text in ("-", "–", "DNS", "DNF", "DSQ"):
        return None
    parts = re.split(r"[:.]", text)
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return None
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3], parts[-2], parts[-1]
    return h * 3600 + m * 60 + s


def slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].split("?")[0]

# ---------------------------------------------------------------------------
# Step 1 — hardcoded championship event list (2015–2025)
# ---------------------------------------------------------------------------
# Avoids scraping the listing page (which never reaches networkidle).
# Slug → (year, tier).  prog_ids are discovered at runtime from the results page.
KNOWN_CHAMPIONSHIP_EVENTS = [
    # World Championship Grand Finals
    ("2015-itu-world-triathlon-grand-final-chicago",              2015, "world_championship"),
    ("2016-itu-world-triathlon-grand-final-cozumel",              2016, "world_championship"),
    ("2017-itu-world-triathlon-grand-final-rotterdam",            2017, "world_championship"),
    ("2018-itu-world-triathlon-grand-final-gold-coast",           2018, "world_championship"),
    ("2019-itu-world-triathlon-grand-final-lausanne",             2019, "world_championship"),
    ("2020-world-triathlon-grand-final-hamburg",                  2020, "world_championship"),
    ("2021-world-triathlon-grand-final-edmonton",                 2021, "world_championship"),
    ("2022-world-triathlon-grand-final-abu-dhabi",                2022, "world_championship"),
    ("2023-world-triathlon-championship-finals-pontevedra",       2023, "world_championship"),
    ("2024-world-triathlon-grand-final-tongyeong",                2024, "world_championship"),
    # Olympic Games
    ("2016-rio-olympic-games-triathlon",                          2016, "olympic_games"),
    ("2020-tokyo-olympic-games-triathlon",                        2021, "olympic_games"),
    ("2024-paris-olympic-games-triathlon",                        2024, "olympic_games"),
    # European Championships (Olympic distance)
    ("2015-itu-world-triathlon-europe-championships-geneva",      2015, "continental"),
    ("2016-itu-world-triathlon-europe-championships-lisbon",      2016, "continental"),
    ("2017-europe-triathlon-championships-kitzbuhel",             2017, "continental"),
    ("2018-europe-triathlon-championships-tartu",                 2018, "continental"),
    ("2019-europe-triathlon-championships-kazan",                 2019, "continental"),
    ("2021-europe-triathlon-championships-granada",               2021, "continental"),
    ("2022-europe-triathlon-championships-munich",                2022, "continental"),
    ("2023-europe-triathlon-championships-seville",               2023, "continental"),
    ("2024-europe-triathlon-championships-cagliari",              2024, "continental"),
    # Americas Championships
    ("2015-itu-triathlon-pan-american-championships",             2015, "continental"),
    ("2017-americas-triathlon-championships-huatulco",            2017, "continental"),
    ("2019-americas-triathlon-championships-lima",                2019, "continental"),
    ("2021-americas-triathlon-championships-lima",                2021, "continental"),
    ("2023-americas-triathlon-championships-brasilia",            2023, "continental"),
    # Asia-Pacific Championships
    ("2015-itu-triathlon-asia-pacific-championships-mooloolaba", 2015, "continental"),
    ("2017-asia-triathlon-championships-beijing",                 2017, "continental"),
    ("2019-asia-triathlon-championships-tiszaujvaros",            2019, "continental"),
    ("2022-asia-triathlon-championships-astana",                  2022, "continental"),
    ("2023-asia-triathlon-championships-jeju",                    2023, "continental"),
    ("2024-asia-triathlon-championships-chengdu",                 2024, "continental"),
    # African Championships
    ("2019-africa-triathlon-championships-hurghada",              2019, "continental"),
    ("2022-africa-triathlon-championships-sharm-el-sheikh",       2022, "continental"),
    ("2023-africa-triathlon-championships-sharm-el-sheikh",       2023, "continental"),
]


def collect_event_urls(page) -> list[dict]:
    """
    Return the hardcoded list of championship events filtered to the study window.
    Also attempts to discover additional events from the listing page (best-effort).
    """
    events = {}

    # Add hardcoded known events first
    for slug, year, tier in KNOWN_CHAMPIONSHIP_EVENTS:
        if START_YEAR <= year <= END_YEAR:
            events[slug] = {
                "slug":     slug,
                "url":      f"{EVENTS_BASE}/{slug}/results",
                "category": tier,
                "year":     year,
            }

    # Best-effort: try to supplement from the listing page
    for cat in CATEGORY_FILTERS:
        listing_url = f"{EVENTS_BASE}/?type=results&categories={cat}"
        print(f"  Trying listing: {listing_url}")
        try:
            page.goto(listing_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(5000)
            for _ in range(5):
                page.evaluate("window.scrollBy(0, 1000)")
                page.wait_for_timeout(800)
            cards = page.query_selector_all("a[href*='/results']")
            for card in cards:
                href = card.get_attribute("href") or ""
                if not href.startswith(EVENTS_BASE):
                    href = EVENTS_BASE + href
                slug = slug_from_url(href)
                year_match = re.search(r"(20\d\d)", slug)
                if year_match:
                    year = int(year_match.group(1))
                    if START_YEAR <= year <= END_YEAR and slug not in events:
                        events[slug] = {"slug": slug, "url": href, "category": cat, "year": year}

        except Exception as e:
            print(f"    (listing page skipped: {e})")
        time.sleep(DELAY)

    return list(events.values())

# ---------------------------------------------------------------------------
# Step 2 — for each event, collect elite program IDs
# ---------------------------------------------------------------------------

def collect_programs(page, event: dict) -> list[dict]:
    """
    Load the event page and find Elite Men / Women program tabs/links.
    Returns [{prog_id, prog_name, results_url}].
    """
    event_url = event["url"].replace("/results", "")
    # The results page shows a program selector
    results_root = event["url"] if "/results" in event["url"] else event_url + "/results"
    page.goto(results_root, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_timeout(8000)  # give JS time to render program selector

    actual_url = page.url
    title = page.title()
    print(f"    → {actual_url}")
    print(f"    → title: {title}")

    programs = []
    # Look for program selector tabs or dropdown
    selectors_to_try = [
        "button[data-program-id]",
        "a[href*='program=']",
        "select option[value]",
        "[class*='program'] a",
        "[class*='tab'] a",
    ]
    for sel in selectors_to_try:
        els = page.query_selector_all(sel)
        for el in els:
            text = (el.inner_text() or "").lower().strip()
            if any(kw in text for kw in ELITE_KEYWORDS):
                prog_id = (
                    el.get_attribute("data-program-id")
                    or _extract_program_id(el.get_attribute("href") or "")
                    or _extract_program_id(el.get_attribute("value") or "")
                )
                if prog_id:
                    results_url = f"{EVENTS_BASE}/{event['slug']}/results?program={prog_id}"
                    programs.append({
                        "prog_id":     prog_id,
                        "prog_name":   el.inner_text().strip(),
                        "results_url": results_url,
                    })
        if programs:
            break

    return programs


def _extract_program_id(text: str) -> str | None:
    m = re.search(r"program[=_]?(\d+)", text, re.IGNORECASE)
    return m.group(1) if m else None

# ---------------------------------------------------------------------------
# Step 3 — extract results table from a rendered results page
# ---------------------------------------------------------------------------

def extract_results(page, results_url: str) -> list[dict]:
    """
    Navigate to a rendered results page and extract the athlete results table.
    Returns a list of dicts with split times in seconds.
    """
    page.goto(results_url, wait_until="domcontentloaded", timeout=45_000)

    # Wait for results table to appear (adjust selector if needed)
    try:
        page.wait_for_selector("table tbody tr, [class*='result-row'], [class*='results'] tr",
                               timeout=20_000)
    except Exception:
        print(f"    WARNING: results table not found at {results_url}")
        return []

    rows = []
    # Try several possible row selectors
    row_selectors = [
        "table tbody tr",
        "[class*='result-row']",
        "[class*='ResultRow']",
        "[class*='results-table'] tr",
    ]
    for sel in row_selectors:
        els = page.query_selector_all(sel)
        if els:
            for el in els:
                row = _parse_row(el)
                if row:
                    rows.append(row)
            break

    return rows


def _parse_row(el) -> dict | None:
    """
    Extract fields from a single result row element.
    Columns on triathlon.org results pages (typical order):
      pos | name | noc | swim | t1 | bike | t2 | run | total | pts
    """
    cells = el.query_selector_all("td, [class*='cell'], [class*='Col']")
    if len(cells) < 6:
        return None

    texts = [c.inner_text().strip() for c in cells]

    # Try to find athlete link for ID
    athlete_id = None
    for c in cells:
        a = c.query_selector("a[href*='/athletes/']")
        if a:
            m = re.search(r"/athletes/(\w+)", a.get_attribute("href") or "")
            if m:
                athlete_id = m.group(1)
            break

    # Heuristic column mapping (pos, name, noc, swim, t1, bike, t2, run, total)
    # Works for the standard 9-column layout; adjust if the site changes
    try:
        return {
            "finish_pos":  texts[0] if texts[0].isdigit() else None,
            "name":        texts[1] if len(texts) > 1 else None,
            "nationality": texts[2] if len(texts) > 2 else None,
            "swim_s":      parse_split(texts[3]) if len(texts) > 3 else None,
            "t1_s":        parse_split(texts[4]) if len(texts) > 4 else None,
            "bike_s":      parse_split(texts[5]) if len(texts) > 5 else None,
            "t2_s":        parse_split(texts[6]) if len(texts) > 6 else None,
            "run_s":       parse_split(texts[7]) if len(texts) > 7 else None,
            "total_s":     parse_split(texts[8]) if len(texts) > 8 else None,
            "athlete_id":  athlete_id,
            "dnf_flag":    texts[0].upper() in {"DNF", "DNS", "DSQ"},
        }
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Meta extraction helpers
# ---------------------------------------------------------------------------

def extract_event_meta(page) -> dict:
    """Pull venue, date, lat/lon from the rendered event page."""
    meta = {}
    for sel, key in [
        ("[class*='venue'], [class*='location']", "venue"),
        ("[class*='date'], time", "date"),
    ]:
        el = page.query_selector(sel)
        if el:
            meta[key] = el.inner_text().strip()
    # lat/lon sometimes in a map link
    map_link = page.query_selector("a[href*='maps.google'], a[href*='maps?']")
    if map_link:
        m = re.search(r"[?&]q=([-\d.]+),([-\d.]+)", map_link.get_attribute("href") or "")
        if m:
            meta["lat"] = float(m.group(1))
            meta["lon"] = float(m.group(2))
    return meta

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed.")
        print("Run: pip install playwright && playwright install chromium")
        return

    print(f"Fallback scraper — {dt.datetime.now().isoformat(timespec='seconds')}")
    print(f"Study window: {START_YEAR}–{END_YEAR}  |  headless={HEADLESS}")

    failures = []
    saved = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=HEADLESS)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36"
        )
        page = ctx.new_page()
        page.set_default_timeout(60_000)

        # Step 1: collect event listing
        print("\nStep 1 — collecting championship event URLs …")
        events = collect_event_urls(page)
        print(f"Found {len(events)} candidate events in study window.\n")

        for ev in events:
            print(f"  Event: {ev['slug']}  ({ev['year']})")

            # Step 2: find elite programs
            try:
                programs = collect_programs(page, ev)
            except Exception as exc:
                failures.append({"event": ev["slug"], "error": f"programs: {exc}"})
                print(f"    FAIL programs: {exc}")
                continue

            if not programs:
                print(f"    SKIP — no Elite Men/Women programs found")
                continue

            # Get meta once per event
            try:
                meta = extract_event_meta(page)
            except Exception:
                meta = {}

            # Step 3: extract results per program
            for prog in programs:
                sex  = "women" if "women" in prog["prog_name"].lower() else "men"
                stem = f"{ev['year']}_{ev['category'].replace('+','_')}_{sex}_{prog['prog_id']}"
                out  = RAW / f"{stem}.json"

                if out.exists():
                    print(f"    SKIP (exists) {stem}")
                    continue

                try:
                    results = extract_results(page, prog["results_url"])
                except Exception as exc:
                    failures.append({"event": ev["slug"], "prog_id": prog["prog_id"], "error": str(exc)})
                    print(f"    FAIL results: {exc}")
                    continue

                payload = {
                    "race_meta": {
                        "race_id":    f"{ev['slug']}_{prog['prog_id']}",
                        "prog_id":    prog["prog_id"],
                        "year":       ev["year"],
                        "tier":       ev["category"],
                        "sex":        sex,
                        "event_name": ev["slug"].replace("-", " ").title(),
                        "prog_name":  prog["prog_name"],
                        "date":       meta.get("date"),
                        "venue":      meta.get("venue"),
                        "lat":        meta.get("lat"),
                        "lon":        meta.get("lon"),
                        "scraper":    "fallback_playwright",
                    },
                    "results": results,
                }
                out.write_text(json.dumps(payload, indent=2, default=str))
                print(f"    OK  {stem}  ({len(results)} athletes)")
                saved += 1

                time.sleep(DELAY)

        browser.close()

    print(f"\nDone. Saved {saved} programs. Failures: {len(failures)}.")
    if failures:
        fail_path = RAW / "_scrape_fallback_failures.json"
        fail_path.write_text(json.dumps(failures, indent=2))
        print(f"Failure log → {fail_path}")
    print("Next step: python src/scrape/build_manifest.py")


if __name__ == "__main__":
    main()
