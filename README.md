# Olympic-Distance Triathlon: Podium, Heat & Digital Twin Study

A research project analysing 10 years of championship Olympic-distance triathlon to (1) characterise
what defines podium performances, (2) reconstruct and profile venue WBGT (heat) conditions,
(3) identify athletes who perform better in the heat, and (4) build a digital twin to help athletes
and coaches plan for races.

Built and run in Claude Cowork. Version-controlled on GitHub.

## Scope decisions (settled)

- **Races:** Olympic-distance only — World Championships (the Grand Final *race*, not series standings),
  continental championships (Olympic-distance editions only), and the Olympic Games.
- **Decade:** rolling last 10 years.
- **Sex:** men and women analysed separately throughout.
- **Format note:** these are draft-legal races — expect the run split and pre-run positioning to be decisive.
- **Field heterogeneity:** championship fields vary in depth, so a field-strength covariate is carried through
  every model.
- **Supplementary corpus:** broader WTCS / World Cup Olympic-distance races may be used as extra training
  volume for the heat model and digital twin, flagged separately from championship-only results.

## Repository structure

```
triathlon-study/
  data/raw/          scraped results, raw weather pulls
  data/interim/      cleaned + standardised tables
  data/processed/    analysis-ready master table
  src/scrape/        connector-driven scraping
  src/wbgt/          WBGT reconstruction + venue climatology
  src/analysis/      podium models, heat models
  src/twin/          digital twin
  outputs/figures/   charts
  outputs/tables/    result tables
  outputs/reports/   final report
  docs/              data dictionary + methods log + this README
```

## Master table (athlete-race grain)

race_id, date, local_start_time, venue, lat, lon, sex, distance, tier (Worlds/Continental/Games),
athlete_id, name, nationality, age, world_ranking_pre, swim_s, t1_s, bike_s, t2_s, run_s, total_s,
finish_pos, dnf_flag — plus derived: within-race z-scores per split, run_split_rank, position_change,
gap_to_leader_pre_run, field_strength metrics, race_day_wbgt, venue_clim_wbgt_pctile.

## Phase plan

**Phase 0 — Acquisition.** Scrape results for the three tiers across the decade via the scraping connector.
Build a race manifest (tier, distance, date, venue) to confirm coverage and exclude sprint-distance
continental races. Log scrape failures.

**Phase 1 — Dataset.** Consolidate raw files, parse splits to seconds, attach world rankings as-of race date,
engineer features (z-scores, run-split rank, position change, pre-run gap, field strength). Men/women in
separate frames. Output `data/processed/master.parquet` + data-quality report.

**Phase 2 — Podium characterisation.** Mixed-effects logistic model (athletes + races as random effects;
splits + field strength as predictors) plus a gradient-boosted classifier with SHAP for interpretable
importance. Deliver figures + results memo. Expect run/positioning dominance, quantified.

**Phase 3 — WBGT.** Per race: hourly weather at venue over the race window (Open-Meteo historical to start,
ERA5/Copernicus for gold-standard radiation), WBGT via the Liljegren model (`pythermalcomfort`). Separately:
multi-year venue climatology for each venue's calendar window, marking where race day fell. Deliver venue
WBGT profile table + distribution plots.

**Phase 4 — Heat tolerance.** Within-athlete model: standardised performance vs WBGT with random slopes per
athlete, controlling for field strength; optionally widen to supplementary corpus for power. Deliver ranked
list with confidence + race counts and cautions for thin heat exposure.

**Phase 5 — Digital twin.** (a) Predictive layer: expected splits/position given athlete history + course +
WBGT scenario. (b) Strain layer: predicted core-temperature trajectory and pacing ceiling via PHS/two-node
models (`pythermalcomfort`). Wrap in an interactive artifact for coaches. Validate on a temporal hold-out.
State clearly: archetype-plus-history model, not an individual physiological clone.

**Phase 6 — Reporting & governance.** Assemble methods log, data dictionary, and memos into one report.
Document WBGT method for reproducibility. Note data-licensing position and ethics of athlete-level findings.

## Sequencing note

Phases 0–1 gate the analysis, but Phase 3's weather work is independent and can run in parallel as soon as
the race manifest (venues + dates) exists.

## Tech stack

pandas; statsmodels (mixed models; pymer4 or Bayesian for random slopes); xgboost + shap;
pythermalcomfort (WBGT + PHS/thermoregulation); Open-Meteo / ERA5 for weather.

## Open items

- Scraping connector for triathlon.org — being connected.
- GitHub connector — being connected; first commit = this README.
- Copernicus CDS key if ERA5 radiation is wanted (Open-Meteo works without one).
