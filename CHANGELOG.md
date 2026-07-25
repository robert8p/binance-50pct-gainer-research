# Changelog

## 9.0.0

- Retired all precursor filters: H1, H2 and H3.
- Replaced the two-stage H3-plus-momentum backtest with a momentum-only continuous test.
- Frozen the untouched test window at 1 July–1 November 2025.
- Evaluates the unchanged three-of-four late-momentum trigger after every completed minute.
- Changed the frozen take-profit from +15% to +10%; retained the -5% stop and three-hour hold.
- Removed the requirement for a passing fresh-confirmation job.
- Added fixed PASS/FAIL graduation criteria.
- Added chronological-third, monthly, daily, symbol and coin-cluster-bootstrap analysis.
- Added maximum favourable/adverse excursion and realised entry/exit slippage to completed trades.
- Preserved all earlier database rows and downloadable research packages.
