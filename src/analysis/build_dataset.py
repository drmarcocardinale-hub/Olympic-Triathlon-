"""
Phase 1 — consolidate raw race JSON into the analysis-ready master table and engineer features.

Reads data/raw/*.json (only races marked include=Y in _manifest.csv), parses splits, attaches
world rankings (point-in-time), and computes within-race z-scores and field-strength measures.
Writes data/processed/master.parquet.

JSON schema (written by scrape_results.py):
  {
    "race_meta": { race_id, event_id, prog_id, year, tier, sex,
                   event_name, prog_name, date, venue, lat, lon, country },
    "program_meta": { ... },
    "results": [ { athlete_id, athlete_title, finish_pos,
                   swim_time, t1_time, bike_time, t2_time, run_time,
                   total_time, ... } ]
  }

triathlon.org API result field name aliases (we normalise all to *_s seconds below):
  finish_pos          → finish_pos
  split_swim          → swim_s
  split_t1            → t1_s
  split_bike          → bike_s
  split_t2            → t2_s
  split_run           → run_s
  total_time          → total_s
"""
from __future__ import annotations
import json
import pathlib
import re
import pandas as pd
import numpy as np
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG  = yaml.safe_load((ROOT / "config.yaml").read_text())
RAW  = ROOT / CFG["paths"]["raw"]
PROC = ROOT / CFG["paths"]["processed"]
TOP_N = CFG["field_strength"]["top_n_threshold"]


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
_TIME_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})$|^(\d+):(\d{2})$")


def _to_seconds(val) -> float | None:
    """Convert 'HH:MM:SS', 'MM:SS', or a bare number (already seconds) to float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if not np.isnan(float(val)) else None
    s = str(val).strip()
    m = _TIME_RE.match(s)
    if m:
        if m.group(1) is not None:          # HH:MM:SS
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        else:                               # MM:SS
            return int(m.group(4)) * 60 + int(m.group(5))
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Known field-name aliases from the triathlon.org API
# ---------------------------------------------------------------------------
_SEG_ALIASES: dict[str, list[str]] = {
    "swim_s": ["split_swim", "swim_time", "swim_s", "t_swim"],
    "t1_s":   ["split_t1",   "t1_time",   "t1_s",   "t_t1"],
    "bike_s": ["split_bike", "bike_time", "bike_s", "t_bike"],
    "t2_s":   ["split_t2",   "t2_time",   "t2_s",   "t_t2"],
    "run_s":  ["split_run",  "run_time",  "run_s",  "t_run"],
    "total_s":["total_time", "total_s",   "t_total"],
}


def _extract_seg(row: dict, key: str) -> float | None:
    for alias in _SEG_ALIASES.get(key, [key]):
        if alias in row:
            return _to_seconds(row[alias])
    return None


# ---------------------------------------------------------------------------
# File selection
# ---------------------------------------------------------------------------
def _included_files() -> list[pathlib.Path]:
    man = RAW / "_manifest.csv"
    if not man.exists():
        return [f for f in RAW.glob("*.json") if not f.name.startswith("_")]
    m = pd.read_csv(man)
    keep = set(m.loc[m["include"].astype(str).str.upper() == "Y", "file"])
    return [RAW / f for f in keep if (RAW / f).exists()]


# ---------------------------------------------------------------------------
# Phase 1a — load raw JSON into long-format DataFrame
# ---------------------------------------------------------------------------
def load_long() -> pd.DataFrame:
    records = []
    for jf in _included_files():
        d = json.loads(jf.read_text())

        # --- schema: race_meta (new API scraper) or meta (legacy) ----------
        rm = d.get("race_meta") or d.get("meta") or {}

        race_id          = rm.get("race_id")
        year             = rm.get("year")
        tier             = rm.get("tier")
        sex              = rm.get("sex")
        venue            = rm.get("venue")
        date             = rm.get("date")
        local_start_time = rm.get("local_start_time")   # may be absent from API data
        lat              = rm.get("lat")
        lon              = rm.get("lon")
        country          = rm.get("country")
        event_name       = rm.get("event_name", rm.get("event"))

        # API stores results as a dict {results: [...], headers: [...], ...}
        # Legacy/fallback: results may already be a list
        results_raw = d.get("results", [])
        if isinstance(results_raw, dict):
            athlete_list = results_raw.get("results", [])
        else:
            athlete_list = results_raw  # legacy list format

        for r in athlete_list:
            # Splits: API returns ["HH:MM:SS", ...] in [swim, t1, bike, t2, run] order
            splits = r.get("splits") or []
            swim_s  = _to_seconds(splits[0]) if len(splits) > 0 else _extract_seg(r, "swim_s")
            t1_s    = _to_seconds(splits[1]) if len(splits) > 1 else _extract_seg(r, "t1_s")
            bike_s  = _to_seconds(splits[2]) if len(splits) > 2 else _extract_seg(r, "bike_s")
            t2_s    = _to_seconds(splits[3]) if len(splits) > 3 else _extract_seg(r, "t2_s")
            run_s   = _to_seconds(splits[4]) if len(splits) > 4 else _extract_seg(r, "run_s")
            total_s = _extract_seg(r, "total_s")  # "total_time" alias already in _SEG_ALIASES

            records.append({
                "race_id":          race_id,
                "year":             year,
                "tier":             tier,
                "sex":              sex,
                "venue":            venue,
                "date":             date,
                "local_start_time": local_start_time,
                "lat":              lat,
                "lon":              lon,
                "country":          country,
                "event_name":       event_name,
                # athlete identity
                "athlete_id":       r.get("athlete_id"),
                "athlete_name":     r.get("athlete_title") or r.get("athlete_name"),
                "athlete_noc":      r.get("athlete_noc"),
                "athlete_yob":      r.get("athlete_yob"),
                "dsq_reason":       r.get("dsq_reason"),
                # finish — API uses "position", legacy used "finish_pos"
                "finish_pos":       r.get("position") if r.get("position") is not None
                                    else r.get("finish_pos"),
                # split times (seconds)
                "swim_s":  swim_s,
                "t1_s":    t1_s,
                "bike_s":  bike_s,
                "t2_s":    t2_s,
                "run_s":   run_s,
                "total_s": total_s,
            })
    return pd.DataFrame.from_records(records)


# ---------------------------------------------------------------------------
# Phase 1b — optional world ranking join
# ---------------------------------------------------------------------------
def attach_rankings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Join point-in-time world ranking as-of each race date.
    Source: scrape triathlon.org/rankings pages separately, save as
    data/interim/rankings_history.csv  (columns: athlete_id, date, world_rank).
    Merge on (athlete_id, nearest ranking date <= race date).
    """
    rank_file = ROOT / CFG["paths"]["interim"] / "rankings_history.csv"
    if rank_file.exists():
        ranks = pd.read_csv(rank_file, parse_dates=["date"])
        df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
        ranks = ranks.sort_values("date")
        df = pd.merge_asof(
            df.sort_values("date_dt"),
            ranks.rename(columns={"date": "rank_date", "world_rank": "world_ranking_pre"}),
            left_on="date_dt", right_on="rank_date",
            left_by="athlete_id", right_by="athlete_id",
            direction="backward",
        )
        df = df.drop(columns=["rank_date", "date_dt"], errors="ignore")
    else:
        df["world_ranking_pre"] = np.nan
    return df


# ---------------------------------------------------------------------------
# Phase 1c — feature engineering
# ---------------------------------------------------------------------------
def engineer(df: pd.DataFrame) -> pd.DataFrame:
    # -- numeric coercion ---------------------------------------------------
    for c in ["swim_s", "t1_s", "bike_s", "t2_s", "run_s", "total_s", "finish_pos"]:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")

    df["dnf_flag"] = (df["total_s"].isna() | df["finish_pos"].isna()
                      | df.get("dsq_reason", pd.Series(None, index=df.index)).notna())
    grp = ["race_id", "sex"]

    # -- infer total_s from segments if missing ----------------------------
    mask = df["total_s"].isna() & df[["swim_s", "t1_s", "bike_s", "t2_s", "run_s"]].notna().all(axis=1)
    df.loc[mask, "total_s"] = (
        df.loc[mask, ["swim_s", "t1_s", "bike_s", "t2_s", "run_s"]].sum(axis=1)
    )

    # -- pre-run cumulative time (swim + T1 + bike + T2) -------------------
    pre_run_cols = ["swim_s", "t1_s", "bike_s", "t2_s"]
    df["cum_pre_run_s"] = df[pre_run_cols].sum(axis=1, min_count=4)  # NaN if any missing

    # -- pre-run rank (rank by cum_pre_run_s within race, lower = faster) --
    df["pre_run_rank"] = (
        df.groupby(grp)["cum_pre_run_s"]
        .rank(method="min", na_option="keep")
        .astype("Float64")
    )

    # -- T2-exit gap to race leader ----------------------------------------
    leader_pre_run = (
        df[~df["dnf_flag"]]
        .groupby(grp)["cum_pre_run_s"]
        .min()
        .rename("leader_cum_pre_run_s")
    )
    df = df.merge(leader_pre_run, on=grp, how="left")
    df["gap_to_leader_pre_run_s"] = df["cum_pre_run_s"] - df["leader_cum_pre_run_s"]
    df = df.drop(columns=["leader_cum_pre_run_s"])

    # -- position change: positive = gained places on the run ---------------
    # finish_pos is the final race rank; pre_run_rank is rank entering the run.
    df["pos_change"] = (df["pre_run_rank"] - df["finish_pos"]).astype("Float64")

    # -- within-race z-scores -----------------------------------------------
    for seg, z in [("swim_s", "z_swim"), ("bike_s", "z_bike"),
                   ("run_s", "z_run"), ("total_s", "z_total")]:
        df[z] = df.groupby(grp)[seg].transform(
            lambda s: (s - s.mean()) / s.std(ddof=0) if s.std(ddof=0) > 0 else np.nan
        )

    # -- run-split rank within race -----------------------------------------
    df["run_split_rank"] = df.groupby(grp)["run_s"].rank(method="min", na_option="keep")

    # -- podium label -------------------------------------------------------
    df["podium"] = (df["finish_pos"] <= 3).astype("Int64")
    df.loc[df["dnf_flag"], "podium"] = pd.NA

    # -- field strength (per race) -----------------------------------------
    fs = (
        df.groupby(grp)["world_ranking_pre"]
        .agg(
            field_strength_mean_rank="mean",
            field_strength_depth=lambda s: (s <= TOP_N).sum(),
        )
        .reset_index()
    )
    df = df.merge(fs, on=grp, how="left")

    return df


# ---------------------------------------------------------------------------
# Phase 1d — WBGT join (if race_wbgt.csv already built by wbgt.py)
# ---------------------------------------------------------------------------
def attach_wbgt(df: pd.DataFrame) -> pd.DataFrame:
    wbgt_file = ROOT / CFG["paths"]["outputs"] / "tables" / "race_wbgt.csv"
    if wbgt_file.exists():
        wbgt = pd.read_csv(wbgt_file)
        merge_cols = [c for c in ["race_id", "sex"] if c in wbgt.columns]
        df = df.merge(wbgt, on=merge_cols, how="left", suffixes=("", "_wbgt"))
        print(f"  Joined WBGT for {wbgt['race_id'].nunique()} races.")
    else:
        print("  WBGT file not found — run wbgt.py first for heat-stress columns.")
        df["wbgt_mean"] = np.nan
        df["wbgt_max"]  = np.nan
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Phase 1 — building master dataset …")
    long = load_long()
    if long.empty:
        print("No included races found in data/raw/.")
        print("Steps: 1) run scrape_results.py  2) run build_manifest.py  3) mark include=Y.")
        return

    print(f"  Loaded {len(long)} athlete-race rows from {long['race_id'].nunique()} races.")
    long = attach_rankings(long)
    master = engineer(long)
    master = attach_wbgt(master)

    PROC.mkdir(parents=True, exist_ok=True)
    out = PROC / "master.parquet"
    master.to_parquet(out, index=False)

    # quick data-quality report
    (ROOT / "outputs" / "tables").mkdir(parents=True, exist_ok=True)
    miss = master.isna().mean().round(3).sort_values(ascending=False)
    miss.to_csv(ROOT / "outputs" / "tables" / "missingness.csv")

    print(f"\nWrote {out}")
    print(f"  {len(master)} athlete-races  ×  {master.shape[1]} columns")
    print(f"  {master['race_id'].nunique()} races  |  "
          f"{master['athlete_id'].nunique()} unique athletes")
    print("\nTop-10 missing columns:")
    print(miss.head(10).to_string())
    print("\nNext: python src/wbgt/wbgt.py  (if not done) then src/analysis/podium_model.py")


if __name__ == "__main__":
    main()
