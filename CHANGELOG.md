# Changelog

## 5.0.0

- Added a baseline-aligned precursor engine anchored to the start minute of the detected surge.
- Added eleven fixed snapshots from ten days before baseline through the baseline itself.
- Separated the frozen 15-minute continuation trigger from precursor analysis.
- Added symmetric pseudo-baselines for controls using matched-event surge duration.
- Added full pseudo-event-window contamination audits for controls.
- Added three frozen precursor hypotheses to every package.
- Added fresh-evidence guards requiring an earlier explicit period and 180-minute contamination protection.
- Added separate baseline-context exploratory, discovery, validation, sealed and index packages.
- Added `binance_baseline_context_jobs`, `binance_baseline_context_files` and `binance_baseline_context_issues`.
- Reduced worker memory usage by processing subject symbols one at a time.
- Preserved all v4 scanning, event archive, matched-control and crossing-aligned context functionality.

## 4.0.0

- Added a full ten-day, multi-timescale context feature engine.
- Added fixed historical scan dates and staged context packages.

## 3.0.0

- Added matched same-coin non-surge controls and staged packages.
