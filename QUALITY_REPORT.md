# Quality report — v5.0.0

## Automated validation completed in the build environment

- 37 network-free tests passed, excluding two unchanged positive-event archive tests that require PyArrow at import time.
- All application and test modules compiled successfully.
- The Jinja dashboard template parsed successfully.
- Event baselines and control pseudo-baselines were verified at symmetric minute resolution.
- Predictor mutation tests verified that baseline-start rows do not use the baseline minute or any later bar.
- The control audit was verified to detect an accidental 50% pseudo-window move.
- A synthetic end-to-end builder smoke test produced the exploratory and index packages.
- The fixed precursor hypotheses and frozen continuation trigger were verified as machine-readable rules.
- The v4-to-v5 migration was scanned for destructive SQL operations.

PyArrow is pinned in `requirements.txt` and installed by GitHub Actions and Render. It was unavailable in this offline packaging environment, so `tests/test_research_bundle.py` and `tests/test_research_cutoff.py` could not be collected locally. The unchanged positive-event archive code was not modified in v5.

## Integrity controls

- All precursor predictors end at the last completed minute before each baseline-relative snapshot.
- Events and controls use minute-level baseline alignment symmetrically.
- Exact event trade data remain metadata/outcomes, not asymmetric predictors.
- Controls are re-audited across the full pseudo-baseline-to-anchor interval.
- The three precursor hypotheses and the continuation trigger are fixed in package metadata.
- Fresh staged mode rejects overlap with the opened May–July period.
- Fresh staged mode requires 180-minute control contamination protection.
- Outcome columns are explicitly prefixed `outcome_`.

## Operational design

The builder holds only BTC/ETH/BNB reference closes plus one subject-symbol frame at a time, reducing memory pressure compared with retaining every symbol frame simultaneously.

## Remaining limitations

Live Binance, Supabase and Render calls were not available in the packaging environment. Deployment should begin with the existing exploratory alignment audit before the larger earlier historical scan.
