# Olympic Triathlon Digital Twin — Monthly Update Log

Automated monthly pipeline log. Each entry records model coefficient changes, data volume, and any anomalies.

---

## Update: 2026-06-18

- New races added: build_manifest.py added to manifest (651 races total); scrape_results.py failed — requires TRIATHLON_API_KEY not set in environment; build_manifest.py used as fallback (no new raw data scraped)
- Total athlete-races: 7,415 (from existing raw data; 339 races with WBGT for 96)
- β_heat_men: -0.003 (p=0.273, not significant) — changed from -0.006
- β_heat_women: +0.002 (p=0.447, not significant) — changed from 0.000
- WBGT mean: 18.72°C (changed from 19.3°C)
- Coefficients changed: yes (β_heat_men Δ=0.003 > threshold; β_heat_women Δ=0.002 > threshold; wbgt_mean Δ=0.58°C)
- Artifact updated: BETA.heat_men, BETA.heat_women, BETA.wbgt_mean, footer n, tooltips
- NORMS unchanged: dataset contains mixed race formats (sprint, cross-triathlon, national championships) producing inflated SDs (swim SD ~454s vs expected ~85s); existing elite Olympic-distance norms retained
- PODIUM thresholds unchanged: median field size in dataset (20 men, 13 women) reflects small national events, not WTS/Olympic fields; existing thresholds retained
- Notes: Mixed-effects models showed convergence warnings (gradient |grad|≈52–162) for both sexes. New coefficients are non-significant (p>0.25); previous β_heat_men=-0.006 (p=0.002) was based on a more curated dataset. Consider re-evaluating dataset filtering to exclude non-Olympic-distance and non-elite races before next update. API key needed for live scraping.
