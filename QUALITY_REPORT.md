# V9 quality report

## Scope

V9 changes the final research stage only. All older scan, event-archive, matched-control, context and confirmation workflows remain available for audit, but they are not inputs to the V9 decision.

## Automated checks completed locally

- 53 network-free tests passed.
- Python compilation passed for application and test files.
- Frozen momentum signal generation passed synthetic look-ahead checks.
- Aggregate-trade entry, +10% take-profit, fee and exit reconstruction passed.
- PASS/FAIL graduation logic passed positive and negative synthetic cases.
- V9 migration and preregistered-protocol contract tests passed.
- Existing V1–V8 compatibility tests passed.
- Monthly-archive optimisation and daily partial-month fallback passed a synthetic cache test.

Two unchanged research-archive tests could not be collected locally because `pyarrow` was unavailable in the packaging environment. `pyarrow==21.0.0` remains pinned in `requirements.txt`; those tests continue to run in GitHub Actions and Render where dependencies install normally.

## Integrity controls

- Historical window fixed to 2025-07-01 through 2025-11-01 exclusive.
- No precursor confirmation required or permitted.
- Signal and trade parameters fixed in code and JSON.
- Same-timestamp selection order fixed before results.
- Maximum five filled entries per UTC day.
- Three-hour same-symbol cooldown after exits or failed execution.
- Exact aggregate-trade ordering used for stop versus take-profit triggers.
- Outcome buffer prevents trades extending beyond the fixed test window.
- Result includes chronological, monthly, daily and symbol concentration analysis.
- Deterministic 10,000-iteration symbol-cluster bootstrap included.

## Known limitations

- Current-universe survivorship bias remains material.
- Aggregate trades are a historical execution proxy, not a reconstructed limit-order book.
- Binance archive availability can vary by symbol and day.
- A formal PASS would still require an implementation review before any live capital is used.
