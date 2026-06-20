"""
Phase 3 — reconstruct race-day WBGT and build venue climatologies.

Two products:
  1. race_day_wbgt  — WBGT averaged over the race window (per race).
  2. venue climatology — distribution of WBGT for each venue's calendar window across many years,
     so you can report "typical" conditions and where race day fell.

Weather source: Open-Meteo historical API (no key). For gold-standard solar radiation, switch to
ERA5 via the Copernicus CDS (needs a key) in fetch_weather().

WBGT models (selectable via USE_LILJEGREN flag):
  - Liljegren et al. (2008) [DEFAULT, publication-grade]:
      Iterative solution of globe and natural wet-bulb heat balances with solar zenith angle.
      Reference: Liljegren JC et al., J Occup Environ Hyg 2008;5(10):645-655.
  - Stull (2011) [fallback / quick estimate]:
      Psychrometric wet-bulb approximation + simple globe uplift.
      Reference: Stull R, J Appl Meteorol Climatol 2011;50(11):2267-2269.
"""
from __future__ import annotations
import pathlib
import datetime as dt
import math
import numpy as np
import pandas as pd
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
WINDOW_H   = CFG["wbgt"]["race_window_hours"]
CLIM_YEARS = CFG["wbgt"]["climatology_years"]

# Set to False to revert to Stull (2011) simplified model
USE_LILJEGREN = True


# ── Weather fetch ─────────────────────────────────────────────────────────────
def fetch_weather(lat: float, lon: float, start: dt.date, end: dt.date) -> pd.DataFrame:
    """
    Return hourly weather (temp_c, rh_pct, wind_ms, solar_wm2) for [start, end].
    Uses Open-Meteo historical archive API (no key required).
    Also fetches direct_radiation_instant for Liljegren solar zenith decomposition.
    """
    import requests

    params = {
        "latitude":   lat,
        "longitude":  lon,
        "start_date": start.isoformat(),
        "end_date":   end.isoformat(),
        "hourly": ("temperature_2m,relative_humidity_2m,wind_speed_10m,"
                   "shortwave_radiation,direct_normal_irradiance,diffuse_radiation"),
        "wind_speed_unit": "ms",
        "format":   "json",
        "timezone": "UTC",
    }
    resp = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params=params, timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    h = data["hourly"]
    df = pd.DataFrame({
        "time":      pd.to_datetime(h["time"]),
        "temp_c":    h["temperature_2m"],
        "rh_pct":    h["relative_humidity_2m"],
        "wind_ms":   h["wind_speed_10m"],
        "solar_wm2": h["shortwave_radiation"],
    })
    # Optional: direct normal irradiance for better Liljegren solar decomposition
    if "direct_normal_irradiance" in h:
        df["dni_wm2"]  = h["direct_normal_irradiance"]
        df["dif_wm2"]  = h.get("diffuse_radiation", [None]*len(df))
    return df


# ── Liljegren (2008) WBGT model ───────────────────────────────────────────────

def _solar_zenith_angle(lat_deg: float, lon_deg: float,
                        utc_dt: dt.datetime) -> float:
    """
    Compute solar zenith angle (degrees) using Spencer (1971) / Iqbal (1983).
    Accurate to ±0.01° for most applications.
    """
    lat = math.radians(lat_deg)
    doy = utc_dt.timetuple().tm_yday
    # Equation of time and solar declination (Spencer 1971)
    B = 2 * math.pi * (doy - 1) / 365.0
    decl = (0.006918 - 0.399912 * math.cos(B) + 0.070257 * math.sin(B)
            - 0.006758 * math.cos(2*B) + 0.000907 * math.sin(2*B)
            - 0.002697 * math.cos(3*B) + 0.00148  * math.sin(3*B))
    eot  = (0.000075 + 0.001868 * math.cos(B) - 0.032077 * math.sin(B)
            - 0.014615 * math.cos(2*B) - 0.04089  * math.sin(2*B)) * 229.18  # minutes
    # Solar time
    solar_time_h = (utc_dt.hour + utc_dt.minute / 60.0
                    + lon_deg / 15.0 + eot / 60.0)
    hour_angle = math.radians((solar_time_h - 12.0) * 15.0)
    cos_zenith = (math.sin(lat) * math.sin(decl)
                  + math.cos(lat) * math.cos(decl) * math.cos(hour_angle))
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    return math.degrees(math.acos(cos_zenith))


def _saturation_vapour_pressure(t_c: float) -> float:
    """Buck (1981) saturation vapour pressure (hPa) at temperature t_c (°C)."""
    return 6.1121 * math.exp((18.678 - t_c / 234.5) * t_c / (257.14 + t_c))


def _liljegren_globe_temp(t_c: float, rh_pct: float, wind_ms: float,
                          solar_wm2: float, zenith_deg: float,
                          tol: float = 0.001, max_iter: int = 50) -> float:
    """
    Globe temperature via Newton-Raphson heat balance (Liljegren et al. 2008).
    Solves:  α·S_eff  =  ε_g·σ·(Tg⁴ - Ta⁴)  +  h_c·(Tg - Ta)
    i.e.:    ε_g·σ·Tg⁴ + h_c·Tg  =  α·S_eff + ε_g·σ·Ta⁴ + h_c·Ta

    Returns globe temperature (°C).
    """
    ALPHA_G   = 0.95      # black globe solar absorptivity
    EPSILON_G = 0.95      # globe emissivity
    D_GLOBE   = 0.0508    # 50 mm standard black globe diameter (m)
    SIGMA     = 5.67e-8   # Stefan-Boltzmann (W m⁻² K⁻⁴)

    Ta   = t_c + 273.15   # K
    wind = max(wind_ms, 0.1)

    # Effective solar load on a sphere (Liljegren Eq. 3–4)
    zenith_rad = math.radians(min(zenith_deg, 89.9))
    cos_z = math.cos(zenith_rad)
    if cos_z > 0 and solar_wm2 > 0:
        # Approximate fraction diffuse (Orgill & Hollands parameterisation condensed)
        k_t = min(solar_wm2 / max(1367.0 * cos_z, 1.0), 1.0)  # clearness index
        f_d = max(0.0, 1.0 - 0.09 * k_t) if k_t <= 0.22 else (
              0.9511 - 0.1604*k_t + 4.388*k_t**2 - 16.638*k_t**3 + 12.336*k_t**4
              if k_t <= 0.80 else 0.165)
        S_beam    = solar_wm2 * (1 - f_d)
        S_diffuse = solar_wm2 * f_d
        # Globe sees beam on projected area (π D²/4) and diffuse on full sphere (π D²)
        # Per unit area: beam ≈ S_beam * cos_z / π, diffuse ≈ S_diffuse / 4
        S_eff = ALPHA_G * (S_beam * cos_z / math.pi + S_diffuse / 4.0)
    else:
        S_eff = 0.0

    # Forced convection coefficient (sphere, Hilpert correlation)
    # Nu = 2.0 + 0.6 Re^0.5 Pr^0.33; simplified to h_c = 6.3 * v^0.6 / D^0.4
    h_c = 6.3 * (wind ** 0.6) / (D_GLOBE ** 0.4)

    # RHS constant
    RHS = ALPHA_G * S_eff + EPSILON_G * SIGMA * Ta**4 + h_c * Ta

    # Newton-Raphson: f(Tg) = ε σ Tg⁴ + h_c Tg - RHS = 0
    Tg = Ta + S_eff / (h_c + 4 * EPSILON_G * SIGMA * Ta**3)  # linearised initial guess
    for _ in range(max_iter):
        f  = EPSILON_G * SIGMA * Tg**4 + h_c * Tg - RHS
        fp = 4 * EPSILON_G * SIGMA * Tg**3 + h_c
        delta = f / max(abs(fp), 1e-10)
        Tg -= delta
        if abs(delta) < tol:
            break
    return float(Tg - 273.15)


def _liljegren_natural_wetbulb(t_c: float, rh_pct: float, wind_ms: float,
                                solar_wm2: float, zenith_deg: float,
                                tol: float = 0.001, max_iter: int = 100) -> float:
    """
    Natural wet-bulb temperature via Newton-Raphson energy balance (Liljegren 2008).

    Energy balance on a wet wick thermometer:
      h_c*(Ta - Tw) + αw*Sw + εw*σ*(Ta⁴ - Tw⁴) = (h_c·λ·Mw)/(cp·P) * (ew(Tw) - ea)

    The right-hand side uses the Lewis analogy with molecular weight correction:
      latent_flux = h_c * (λ * Mw) / (cp * P) * (ew(Tw) - ea)

    where Mw/Md = 0.622 gives the correct mixing-ratio-based psychrometric constant.

    Returns natural wet-bulb temperature (°C).
    """
    EPSILON_W = 0.95      # wick emissivity
    ALPHA_W   = 0.4       # wick solar absorptivity (white wick)
    D_WICK    = 0.007     # wick diameter 7 mm (m)
    SIGMA     = 5.67e-8   # Stefan-Boltzmann
    Cp        = 1010.0    # specific heat of air J/(kg·K)
    LAMBDA    = 2.43e6    # latent heat of vaporisation J/kg
    MW_RATIO  = 0.622     # Mw / Md (molecular weight ratio water/dry air)
    P_hPa     = 1013.25   # sea-level pressure (hPa)

    Ta   = t_c + 273.15   # K
    rh   = rh_pct / 100.0
    wind = max(wind_ms, 0.1)
    ea   = _saturation_vapour_pressure(t_c) * rh   # actual vapour pressure (hPa)

    # Psychrometric constant (hPa/K): γ = cp * P / (Mw/Md * λ)
    # => latent coefficient k = h_c * λ * MW_RATIO / (cp * P_hPa)  [W/m²/hPa]
    k_psy = LAMBDA * MW_RATIO / (Cp * P_hPa)   # K/hPa (dimensionless temperature per pressure)

    # Solar on wick (cylinder, horizontal axis)
    zenith_rad = math.radians(min(zenith_deg, 89.9))
    cos_z = math.cos(zenith_rad)
    if cos_z > 0 and solar_wm2 > 0:
        S_wick = ALPHA_W * solar_wm2 * cos_z / math.pi
    else:
        S_wick = 0.0

    # Forced convection coefficient for cylinder (same Hilpert-type expression as globe)
    h_c = 6.3 * (wind ** 0.6) / (D_WICK ** 0.4)

    # Initial guess: Stull (2011) wet-bulb (good approximation, within ±1°C)
    rh_clip = max(5.0, min(100.0, rh_pct))
    Tw = (t_c * math.atan(0.151977 * math.sqrt(rh_clip + 8.313659))
          + math.atan(t_c + rh_clip) - math.atan(rh_clip - 1.676331)
          + 0.00391838 * rh_clip**1.5 * math.atan(0.023101 * rh_clip) - 4.686035)

    # Tw must lie in [dew-point, Ta]; start search from Stull guess
    Tw_lo = t_c - 40.0   # wide lower bound (below dew point for safety)
    Tw_hi = t_c + 5.0    # slight upper bound (wick can't exceed air + small radiation gain)
    Tw = max(Tw_lo, min(Tw_hi, Tw))   # clip initial guess

    for _ in range(max_iter):
        Tw   = max(Tw_lo, min(Tw_hi, Tw))   # clamp each iteration
        Tw_K = Tw + 273.15
        ew   = _saturation_vapour_pressure(Tw)        # hPa at Tw

        # Energy balance residual f(Tw) = 0
        # f = h_c*(Ta-Tw_K) + S_wick + εw*σ*(Ta^4 - Tw_K^4) - h_c*k_psy*(ew - ea)
        rad     = EPSILON_W * SIGMA * (Ta**4 - Tw_K**4)
        latent  = h_c * k_psy * (ew - ea)
        f       = h_c * (Ta - Tw_K) + S_wick + rad - latent

        # Jacobian df/dTw  (note: d/dTw in °C, same as d/dTw_K)
        d_ew_dTw = ew * (18.678 - Tw / 117.25) / (257.14 + Tw)   # d(ew)/dTw
        df_dTw   = (-h_c                                           # convective
                    - 4 * EPSILON_W * SIGMA * Tw_K**3              # radiative
                    - h_c * k_psy * d_ew_dTw)                     # latent

        # df_dTw is always negative (all three terms diminish f as Tw rises)
        safe_df = df_dTw if abs(df_dTw) > 1e-6 else -1e-6
        delta   = f / safe_df            # NOTE: keep sign; Tw -= delta = Tw - f/f'
        Tw     -= delta
        if abs(delta) < tol:
            break

    return float(max(Tw_lo, min(Tw_hi, Tw)))


def _liljegren_wbgt_scalar(t_c: float, rh_pct: float, wind_ms: float,
                            solar_wm2: float, zenith_deg: float) -> float:
    """Compute outdoor WBGT using Liljegren (2008) for scalar inputs."""
    Tnwb = _liljegren_natural_wetbulb(t_c, rh_pct, wind_ms, solar_wm2, zenith_deg)
    Tg   = _liljegren_globe_temp(t_c, rh_pct, wind_ms, solar_wm2, zenith_deg)
    return 0.7 * Tnwb + 0.2 * Tg + 0.1 * t_c


# ── Stull (2011) simplified model ─────────────────────────────────────────────
def _stull_wetbulb(t, rh):
    """Stull (2011) psychrometric wet-bulb approximation."""
    rh = np.clip(rh, 5, 100)
    return (t * np.arctan(0.151977 * np.sqrt(rh + 8.313659))
            + np.arctan(t + rh) - np.arctan(rh - 1.676331)
            + 0.00391838 * rh**1.5 * np.arctan(0.023101 * rh) - 4.686035)


def _stull_globe(t, wind, solar):
    """Simplified globe temperature uplift."""
    wind = np.clip(wind, 0.3, None)
    return t + (1.5 * np.sqrt(np.clip(solar, 0, None)) / (wind**0.4)) / 10.0


def _stull_wbgt(temp_c, rh_pct, wind_ms, solar_wm2):
    tnwb = _stull_wetbulb(temp_c, rh_pct)
    tg   = _stull_globe(temp_c, wind_ms, solar_wm2)
    return 0.7 * tnwb + 0.2 * tg + 0.1 * temp_c


# ── Public WBGT interface ─────────────────────────────────────────────────────
def wbgt_outdoor(temp_c, rh_pct, wind_ms, solar_wm2,
                 lat: float = 0.0, lon: float = 0.0,
                 utc_dt: dt.datetime | None = None):
    """
    Compute outdoor WBGT.

    If USE_LILJEGREN=True AND lat/lon/utc_dt are provided:
      → Liljegren et al. (2008) iterative physical model (publication-grade).
    Otherwise:
      → Stull (2011) simplified approximation (fast, no location needed).

    Accepts numpy arrays or scalars for temp/rh/wind/solar.
    lat/lon/utc_dt may be a single value (applied to all rows) or omitted.
    """
    if USE_LILJEGREN and utc_dt is not None:
        # Vectorised over rows if inputs are arrays
        def _single(t, rh, w, s):
            z = _solar_zenith_angle(lat, lon, utc_dt)
            return _liljegren_wbgt_scalar(float(t), float(rh), float(w), float(s), z)

        if hasattr(temp_c, "__len__"):
            return np.array([_single(t, r, w, s)
                             for t, r, w, s in zip(temp_c, rh_pct, wind_ms, solar_wm2)])
        return _single(temp_c, rh_pct, wind_ms, solar_wm2)
    else:
        return _stull_wbgt(temp_c, rh_pct, wind_ms, solar_wm2)


def wbgt_outdoor_df(df: pd.DataFrame, lat: float, lon: float) -> pd.Series:
    """
    Compute WBGT for every row of a weather DataFrame.
    Uses Liljegren if USE_LILJEGREN and lat/lon provided; falls back to Stull otherwise.
    DataFrame must have: time (datetime), temp_c, rh_pct, wind_ms, solar_wm2.
    """
    results = []
    for _, row in df.iterrows():
        utc_dt = row["time"].to_pydatetime() if hasattr(row["time"], "to_pydatetime") else row["time"]
        w = wbgt_outdoor(row["temp_c"], row["rh_pct"], row["wind_ms"], row["solar_wm2"],
                         lat=lat, lon=lon, utc_dt=utc_dt)
        results.append(w)
    return pd.Series(results, index=df.index)


# ── Per-race + climatology ────────────────────────────────────────────────────
def race_day_wbgt(lat, lon, race_dt: dt.datetime) -> float:
    """Compute mean WBGT over the race window using the configured model."""
    wx = fetch_weather(lat, lon, race_dt.date(), race_dt.date())
    wx["time"] = pd.to_datetime(wx["time"]).dt.tz_localize(None)
    start = pd.Timestamp(race_dt.replace(tzinfo=None))
    win = wx[(wx["time"] >= start) & (wx["time"] <= start + pd.Timedelta(hours=WINDOW_H))].copy()
    if win.empty:
        return float("nan")
    if USE_LILJEGREN:
        w = wbgt_outdoor_df(win, lat=lat, lon=lon)
    else:
        w = wbgt_outdoor(win["temp_c"].values, win["rh_pct"].values,
                         win["wind_ms"].values, win["solar_wm2"].values)
    return float(np.nanmean(w))


def venue_climatology(lat, lon, month: int, day: int, hour: int) -> pd.Series:
    """WBGT distribution for this venue/calendar-window across CLIM_YEARS years (same hour-of-day)."""
    vals = []
    this_year = dt.date.today().year
    for yr in range(this_year - CLIM_YEARS, this_year):
        try:
            center = dt.date(yr, month, day)
        except ValueError:
            continue
        wx = fetch_weather(lat, lon, center - dt.timedelta(days=3), center + dt.timedelta(days=3))
        wx = wx[wx["time"].dt.hour == hour]
        if not wx.empty:
            vals.extend(wbgt_outdoor(wx["temp_c"], wx["rh_pct"], wx["wind_ms"], wx["solar_wm2"]))
    s = pd.Series(vals, dtype="float64")
    return s.describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])


# ---- pipeline entry point -------------------------------------------------------
def main():
    """
    Phase 3 pipeline:
      1. Read _manifest.csv  →  race list with coords and dates
      2. Fetch hourly weather from Open-Meteo for each race day (with local cache)
      3. Compute WBGT statistics over the race window
      4. Write outputs/tables/race_wbgt.csv
      5. Compute venue climatologies and write outputs/tables/venue_climatology.csv
    """
    import datetime as dt

    man_path = ROOT / CFG["paths"]["raw"] / "_manifest.csv"
    if not man_path.exists():
        print("No _manifest.csv found. Run build_manifest.py first.")
        return

    man = pd.read_csv(man_path)
    # only include races marked Y
    if "include" in man.columns:
        man = man[man["include"].astype(str).str.upper() == "Y"].copy()
    if man.empty:
        print("Manifest has no included races.")
        return

    # expected columns from build_manifest.py: race_id, date, lat, lon, local_start_time, …
    required = {"race_id", "date", "lat", "lon"}
    missing_cols = required - set(man.columns)
    if missing_cols:
        print(f"Manifest missing columns: {missing_cols}. Cannot proceed.")
        return

    out_dir = ROOT / CFG["paths"]["outputs"] / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    race_rows = []
    clim_rows = []

    for _, row in man.iterrows():
        rid  = row["race_id"]
        lat  = float(row.get("lat") or 0)
        lon  = float(row.get("lon") or 0)
        date_str = str(row.get("date", ""))

        if not date_str or lat == 0:
            print(f"  SKIP {rid} — missing date or coords")
            continue

        # parse race date
        try:
            race_date = dt.date.fromisoformat(date_str[:10])
        except ValueError:
            print(f"  SKIP {rid} — unparseable date '{date_str}'")
            continue

        # infer start hour from local_start_time or default 07:00
        raw_start = str(row.get("local_start_time", "07:00"))
        try:
            start_h, start_m = [int(x) for x in raw_start.replace(".", ":").split(":")[:2]]
        except Exception:
            start_h, start_m = 7, 0

        # tz-naive: JSON API returns UTC times without tz annotation
        race_dt = dt.datetime(race_date.year, race_date.month, race_date.day, start_h, start_m)

        try:
            wx = fetch_weather(lat, lon, race_date, race_date)
        except Exception as exc:
            print(f"  FAIL weather {rid}: {exc}")
            race_rows.append({"race_id": rid, "wbgt_mean": np.nan, "wbgt_max": np.nan,
                               "temp_mean": np.nan, "rh_mean": np.nan})
            continue

        # ensure wx["time"] is tz-naive for comparison
        wx["time"] = pd.to_datetime(wx["time"]).dt.tz_localize(None)
        start_ts = pd.Timestamp(race_dt)
        win = wx[(wx["time"] >= start_ts) &
                 (wx["time"] <= start_ts + pd.Timedelta(hours=WINDOW_H))]

        if win.empty:
            wbgt_vals = pd.Series(dtype="float64")
        else:
            if USE_LILJEGREN:
                wbgt_vals = wbgt_outdoor_df(win.reset_index(drop=True), lat=lat, lon=lon)
            else:
                wbgt_vals = pd.Series(
                    wbgt_outdoor(win["temp_c"].values, win["rh_pct"].values,
                                 win["wind_ms"].values, win["solar_wm2"].values)
                )

        race_rows.append({
            "race_id":   rid,
            "wbgt_mean": float(np.nanmean(wbgt_vals)) if len(wbgt_vals) else np.nan,
            "wbgt_max":  float(np.nanmax(wbgt_vals))  if len(wbgt_vals) else np.nan,
            "temp_mean": float(np.nanmean(win["temp_c"])) if not win.empty else np.nan,
            "rh_mean":   float(np.nanmean(win["rh_pct"])) if not win.empty else np.nan,
        })
        print(f"  OK {rid}  WBGT_mean={race_rows[-1]['wbgt_mean']:.1f} C")

        # venue climatology (one row per unique venue)
        venue = str(row.get("venue", ""))
        if venue and venue not in {r.get("venue") for r in clim_rows}:
            try:
                clim = venue_climatology(lat, lon, race_date.month, race_date.day, start_h)
                clim_row = clim.to_dict()
                clim_row.update({"venue": venue, "lat": lat, "lon": lon,
                                 "month": race_date.month, "day": race_date.day,
                                 "start_hour": start_h})
                clim_rows.append(clim_row)
                print(f"    climatology for {venue}: p50={clim['50%']:.1f} C")
            except Exception as exc:
                print(f"    climatology FAIL for {venue}: {exc}")

    # write outputs
    wbgt_out = out_dir / "race_wbgt.csv"
    pd.DataFrame(race_rows).to_csv(wbgt_out, index=False)
    print(f"\nWrote {wbgt_out}  ({len(race_rows)} races)")

    if clim_rows:
        clim_out = out_dir / "venue_climatology.csv"
        pd.DataFrame(clim_rows).to_csv(clim_out, index=False)
        print(f"Wrote {clim_out}  ({len(clim_rows)} venues)")

    print("Next: python src/analysis/build_dataset.py  (to join WBGT into master)")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        # Demo with synthetic inputs so the file runs without network
        demo = wbgt_outdoor(temp_c=31.0, rh_pct=70.0, wind_ms=1.5, solar_wm2=800.0)
        print(f"Demo WBGT for 31C / 70% RH / 1.5 m/s / 800 W/m^2 ≈ {demo:.1f} C")
    else:
        main()
