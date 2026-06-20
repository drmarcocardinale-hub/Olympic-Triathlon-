"""
Phase 0 — build a race manifest from the scraped raw files so you can eyeball coverage and
flag continental races that are sprint distance for exclusion.

Output: data/raw/_manifest.csv  (review this by hand before Phase 1).
"""
from __future__ import annotations
import json
import pathlib
import pandas as pd
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
RAW = ROOT / CFG["paths"]["raw"]


def main():
    rows = []
    for jf in sorted(RAW.glob("*.json")):
        if jf.name.startswith("_"):
            continue
        d = json.loads(jf.read_text())
        rm = d.get("race_meta", {})
        meta = d.get("meta", {})
        n = len(d.get("results", []))
        rows.append({
            "file": jf.name,
            "race_id": rm.get("race_id"),
            "year": rm.get("year"),
            "tier": rm.get("tier"),
            "sex": rm.get("sex"),
            "venue": rm.get("venue") or meta.get("venue"),
            "date": rm.get("date") or meta.get("date"),
            "lat": rm.get("lat"),
            "lon": rm.get("lon"),
            "country": rm.get("country"),
            "event_name": rm.get("event_name", meta.get("event")),
            "n_athletes": n,
            # Auto-mark include: world_championship and olympic_games are always in scope.
            # Continental events need review — cross/sprint distances occasionally sneak in.
            "include": "Y" if rm.get("tier") in ("world_championship", "olympic_games") else "REVIEW",
        })
    if not rows:
        print("No scraped races found yet — run scrape_results.py first.")
        return
    df = pd.DataFrame(rows).sort_values(["year", "tier", "sex"])
    out = RAW / "_manifest.csv"
    df.to_csv(out, index=False)
    print(f"Wrote {out} with {len(df)} races.")
    print(df.groupby(["tier", "sex"]).size().to_string())


if __name__ == "__main__":
    main()
