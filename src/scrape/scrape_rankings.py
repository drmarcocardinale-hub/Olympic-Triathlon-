"""
Phase 0b — scrape point-in-time World Triathlon rankings.

Fetches the World Triathlon rankings for each month that has at least one race in
the manifest, building a longitudinal table:
    athlete_id | athlete_name | date | world_rank | points | sex

Output: data/interim/rankings_history.csv

The master dataset builder (build_dataset.py) joins this table via merge_asof
on (athlete_id, date) to produce point-in-time rankings for each race.

API endpoint:
  GET /v1/rankings/{rankingId}
  rankingId: 1 = Elite Men, 2 = Elite Women (World Triathlon Points List)
  Optional params: page, per_page, date (YYYY-MM-DD)

Usage:
  export TRIATHLON_API_KEY="your_key_here"
  python src/scrape/scrape_rankings.py          # scrape all months 2015-2025
  python src/scrape/scrape_rankings.py --year 2024  # single year
"""
from __future__ import annotations
import os, sys, time, json, pathlib, datetime as dt
import pandas as pd
import requests
import yaml

ROOT   = pathlib.Path(__file__).resolve().parents[2]
CFG    = yaml.safe_load((ROOT / "config.yaml").read_text())
OUT    = ROOT / CFG["paths"]["interim"]
OUT.mkdir(parents=True, exist_ok=True)

API_KEY  = os.environ.get("TRIATHLON_API_KEY", "c4945b8840fc7b0b273753f95c502b37")
BASE_URL = "https://api.triathlon.org/v1"
HEADERS  = {"apikey": API_KEY}

RANKING_IDS = {
    "men":   1,   # Elite Men — World Triathlon Points List
    "women": 2,   # Elite Women
}

# Fetch one page of rankings for a given ranking_id and date
def _fetch_rankings_page(ranking_id: int, date_str: str, page: int = 1, per_page: int = 200) -> dict:
    url = f"{BASE_URL}/rankings/{ranking_id}"
    params = {"date": date_str, "page": page, "per_page": per_page}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_rankings_for_date(sex: str, date: dt.date) -> list[dict]:
    """Return all ranked athletes for a given sex and date."""
    ranking_id = RANKING_IDS[sex]
    date_str   = date.isoformat()
    rows = []
    page = 1
    while True:
        try:
            data = _fetch_rankings_page(ranking_id, date_str, page=page, per_page=200)
        except requests.HTTPError as e:
            print(f"  HTTP error for {sex} rankings on {date_str} p{page}: {e}")
            break
        results = data.get("data", data.get("results", []))
        if isinstance(results, dict):
            results = results.get("rankings", results.get("results", []))
        if not results:
            break
        for r in results:
            rows.append({
                "athlete_id":   r.get("athlete_id") or r.get("id"),
                "athlete_name": r.get("athlete_title") or r.get("name"),
                "athlete_noc":  r.get("athlete_noc") or r.get("noc"),
                "date":         date_str,
                "sex":          sex,
                "world_rank":   r.get("position") or r.get("rank"),
                "points":       r.get("total") or r.get("points"),
            })
        # Pagination: stop if we got fewer than per_page
        if len(results) < 200:
            break
        page += 1
        time.sleep(0.3)
    return rows


def dates_to_scrape(start_year: int = 2015, end_year: int = 2025) -> list[dt.date]:
    """
    Return the first day of every month from start_year to end_year.
    Rankings update ~monthly so this gives good point-in-time coverage.
    """
    dates = []
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            d = dt.date(year, month, 1)
            if d <= dt.date.today():
                dates.append(d)
    return dates


def main(start_year: int = 2015, end_year: int = 2025, resume: bool = True):
    """
    Scrape rankings for all months in [start_year, end_year].
    Appends to existing rankings_history.csv if resume=True (safe to re-run).
    """
    out_path = OUT / "rankings_history.csv"

    # Load existing data to support resume
    if resume and out_path.exists():
        existing = pd.read_csv(out_path, dtype={"athlete_id": str})
        done_keys = set(zip(existing["sex"], existing["date"].str[:7]))  # (sex, YYYY-MM)
        print(f"Resuming — {len(existing)} existing rows, {len(done_keys)} month-sex combos done.")
    else:
        existing = pd.DataFrame()
        done_keys = set()

    all_rows = []
    dates = dates_to_scrape(start_year, end_year)
    total = len(dates) * 2
    done  = 0

    for date in dates:
        for sex in ["men", "women"]:
            key = (sex, date.strftime("%Y-%m"))
            done += 1
            if key in done_keys:
                continue
            print(f"  [{done}/{total}] {sex} rankings {date.isoformat()} …", end=" ", flush=True)
            rows = fetch_rankings_for_date(sex, date)
            print(f"{len(rows)} athletes")
            all_rows.extend(rows)
            time.sleep(0.5)  # be polite to the API

    if not all_rows and existing.empty:
        print("No data retrieved.")
        return

    new_df = pd.DataFrame(all_rows)
    combined = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
    combined = combined.drop_duplicates(subset=["athlete_id", "sex", "date"])
    combined = combined.sort_values(["sex", "date", "world_rank"])
    combined.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}  ({len(combined):,} rows, "
          f"{combined['athlete_id'].nunique()} unique athletes)")
    print("Next: python src/analysis/build_dataset.py  (to rejoin rankings into master)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scrape World Triathlon point-in-time rankings")
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year",   type=int, default=2025)
    parser.add_argument("--year",       type=int, help="Shortcut: scrape a single year")
    parser.add_argument("--no-resume",  action="store_true")
    args = parser.parse_args()

    if args.year:
        args.start_year = args.end_year = args.year

    main(args.start_year, args.end_year, resume=not args.no_resume)
