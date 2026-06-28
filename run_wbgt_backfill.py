#!/usr/bin/env python3
"""
WBGT Backfill Script
====================
Run this from Terminal ONCE to fetch weather for all 251 races that are
currently missing WBGT data. Requires internet access.

Usage:
    cd ~/Downloads/files/triathlon-study
    python ~/Documents/Claude/Projects/Olympic\ Triathlon\ Study/run_wbgt_backfill.py

Takes ~5-10 minutes. Progress is printed as it runs. Results are cached so
you can safely re-run if interrupted — it skips already-fetched races.
"""
import sys, pathlib, datetime as dt, time
import numpy as np, pandas as pd, requests

# ── Paths ─────────────────────────────────────────────────────────────────────
STUDY  = pathlib.Path(__file__).resolve().parent.parent.parent / "Downloads/files/triathlon-study"
if not (STUDY / "data/processed/master.parquet").exists():
    # Try relative to script
    STUDY = pathlib.Path.home() / "Downloads/files/triathlon-study"
    if not (STUDY / "data/processed/master.parquet").exists():
        print("ERROR: Cannot find triathlon-study folder.")
        print("Edit STUDY path in this script to point to your triathlon-study directory.")
        sys.exit(1)

sys.path.insert(0, str(STUDY))
from src.wbgt.wbgt import wbgt_outdoor_df, wbgt_outdoor, USE_LILJEGREN

MASTER = STUDY / "data/processed/master.parquet"
CACHE  = STUDY / "data/wbgt_backfill_cache.csv"
WINDOW_H = 3   # hours of race window (swim + T1 + early bike)

print(f"Study directory: {STUDY}")
print(f"master.parquet:  {MASTER}")

# ── Load master ───────────────────────────────────────────────────────────────
df = pd.read_parquet(MASTER)

races = (df.groupby('race_id')
           .agg(lat=('lat','first'), lon=('lon','first'),
                date=('date','first'), wbgt=('race_day_wbgt','first'))
           .reset_index())

missing = races[
    races['wbgt'].isna() &
    races['lat'].notna() & races['lon'].notna() &
    races['date'].notna()
].copy()

print(f"\nTotal races:       {len(races)}")
print(f"Already have WBGT: {races['wbgt'].notna().sum()}")
print(f"Need to fetch:     {len(missing)}\n")

# Load cache
cache = {}
if CACHE.exists():
    for _, r in pd.read_csv(CACHE).iterrows():
        cache[r['race_id']] = float(r['wbgt_mean'])
    print(f"Cache: {len(cache)} entries already fetched\n")

def fetch_weather(lat, lon, date):
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": date.isoformat(), "end_date": date.isoformat(),
        "hourly": ("temperature_2m,relative_humidity_2m,wind_speed_10m,"
                   "shortwave_radiation,direct_normal_irradiance,diffuse_radiation"),
        "wind_speed_unit": "ms", "format": "json", "timezone": "UTC",
    }
    r = requests.get("https://archive-api.open-meteo.com/v1/archive",
                     params=params, timeout=30)
    r.raise_for_status()
    h = r.json()["hourly"]
    return pd.DataFrame({
        "time":      pd.to_datetime(h["time"]),
        "temp_c":    h["temperature_2m"],
        "rh_pct":    h["relative_humidity_2m"],
        "wind_ms":   h["wind_speed_10m"],
        "solar_wm2": h["shortwave_radiation"],
    })

results = dict(cache)
failed  = []
today   = dt.date.today()

for i, row in missing.iterrows():
    rid = row['race_id']
    if rid in results:
        continue

    try:
        race_date = dt.date.fromisoformat(str(row['date'])[:10])
    except ValueError:
        continue

    if race_date > today:
        print(f"  SKIP {rid}: future race {race_date}")
        continue

    lat, lon = float(row['lat']), float(row['lon'])

    try:
        wx = fetch_weather(lat, lon, race_date)
        wx["time"] = pd.to_datetime(wx["time"]).dt.tz_localize(None)

        # Race window: default 07:00 UTC start (most elite tri races)
        start = pd.Timestamp(race_date.year, race_date.month, race_date.day, 7, 0)
        win = wx[(wx["time"] >= start) & (wx["time"] <= start + pd.Timedelta(hours=WINDOW_H))]
        if win.empty:
            win = wx   # fall back to full day

        if USE_LILJEGREN:
            wbgt_vals = wbgt_outdoor_df(win.reset_index(drop=True), lat=lat, lon=lon)
        else:
            wbgt_vals = pd.Series(wbgt_outdoor(
                win["temp_c"].values, win["rh_pct"].values,
                win["wind_ms"].values, win["solar_wm2"].values))

        wbgt_mean = float(np.nanmean(wbgt_vals))
        results[rid] = wbgt_mean

        done = len(results) - len(cache)
        remaining = len(missing) - len(cache) - done
        print(f"  [{done}/{len(missing)-len(cache)}] {rid}  {race_date}  "
              f"lat={lat:.1f} lon={lon:.1f}  WBGT={wbgt_mean:.1f}°C")

        # Save cache after each race
        pd.DataFrame([{'race_id': k, 'wbgt_mean': v}
                      for k, v in results.items()]).to_csv(CACHE, index=False)
        time.sleep(0.15)

    except Exception as e:
        print(f"  FAIL {rid}: {e}")
        failed.append(rid)
        time.sleep(0.5)

print(f"\n{'='*60}")
print(f"Fetched: {len(results) - len(cache)} new races")
print(f"Failed:  {len(failed)}")

# ── Merge back into master.parquet ────────────────────────────────────────────
df2 = pd.read_parquet(MASTER)
df2['race_id'] = df2['race_id'].astype(str)
wbgt_map = pd.Series(results)

filled_mask = df2['race_day_wbgt'].isna() & df2['race_id'].isin(wbgt_map.index)
df2.loc[filled_mask, 'race_day_wbgt'] = df2.loc[filled_mask, 'race_id'].map(wbgt_map)

n_races_before = df.groupby('race_id')['race_day_wbgt'].first().notna().sum()
n_races_after  = df2.groupby('race_id')['race_day_wbgt'].first().notna().sum()

print(f"\nWBGT coverage:")
print(f"  Before: {n_races_before}/{df['race_id'].nunique()} races")
print(f"  After:  {n_races_after}/{df2['race_id'].nunique()} races")

w = df2.dropna(subset=['race_day_wbgt'])['race_day_wbgt']
print(f"\nWBGT stats (row-level):")
print(f"  Range: {w.min():.1f}–{w.max():.1f}°C")
print(f"  Mean ± SD: {w.mean():.1f} ± {w.std():.1f}°C")

df2.to_parquet(MASTER, index=False)
print(f"\nSaved updated master.parquet  ✓")
print("\nNext step: run the analysis re-run script or open Cowork and ask Claude to")
print("'re-run all key analyses and update the manuscript statistics'.")
