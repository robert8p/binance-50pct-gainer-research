# Quality report — v3.0.0

## Automated validation

The release passes **26 network-free tests** covering the original v2 scanner and research collector plus:

- chronological split assignment without dividing UTC dates;
- conservative rolling-crossing detection;
- exclusion of current and future minutes from predictors;
- same-symbol control selection;
- exclusion of controls near known events and other 50% crossings;
- matched-control database contract and row-level-security activation.

Additional checks performed:

```text
pytest: 26 passed
Python compilation: passed
synthetic end-to-end matched-package build: passed
current 63-event calendar-capacity simulation: 315/315 controls available
pinned dependency installation: passed
```

## Research-integrity choices

- Controls stay within the same chronological split as their event.
- Matching uses coin identity and calendar variables, not possible predictive features.
- Controls must be outside a contamination interval around every detected 50% crossing.
- One control date contributes at most one control to a given event.
- Predictor bars must be complete before the decision timestamp.
- Feature rows preserve event and symbol cluster identifiers.
- The index package excludes all split feature matrices.
- The sealed-test package is produced separately and clearly labelled.

## Remaining limitations

- Live Binance, Supabase and Render calls are not executed by the offline test suite.
- Historical Binance archive availability can vary; missing files are disclosed and the newest completed day can fall back to the public REST endpoint.
- Current-universe survivorship bias remains for the initial 60-day census.
- The matched round uses one-minute data symmetrically. Event-only one-second and aggregate-trade data must not be used for case-control claims.
- Five controls per event improve comparison but do not create 315 independent observations; inference must cluster by event and coin.
