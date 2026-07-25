# V10.1 quality report

## Scope

V10.1 changes the neutral export period to 2026 year to date without turning the app into a pattern engine.

## Integrity protections

- Fixed source window: 2026-01-01 to 2026-07-25 exclusive.
- All 2026 evidence is labelled exploratory discovery-only.
- No validation or sealed claim is created from previously opened 2026 observations.
- Event and control baselines use the same 480-minute rolling-minimum algorithm.
- Controls with a future 50% rise, proximity to known events, incomplete history or reused baselines are rejected.
- Raw histories are not imputed.
- The app contains no predictor, feature ranking, threshold search, model or trading rule.

## Operational considerations

The scan covers 205 completed UTC days, so the explicit-date limit is raised from 180 to 240 days. Deduplicated Parquet and monthly Binance archives remain in use.

## Remaining limitations

- The historical universe starts from symbols currently reported as tradeable by Binance.
- Five controls per event are a sampled comparison, not all non-event minutes.
- The export omits raw aggregate trades at this discovery stage due to size.
- Any pattern found from 2026 must be tested on separately collected earlier data.

## Validation performed

- 63 network-free tests passed.
- Python compilation passed.
- Jinja template parsing passed.
- FastAPI health smoke test returned version 10.1.0.
- Two legacy PyArrow-dependent tests could not be collected in this offline environment; PyArrow remains pinned for Render and GitHub Actions.
