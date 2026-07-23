# V6 quality report

## Automated checks

- 43 network-free tests passed.
- Python compilation passed for every application module.
- V6 schema and additive-migration checks passed.
- Frozen confirmation-criteria tests passed.
- Vectorised H1-plus-continuation signal tests passed.
- Executed buyer-side entry and seller-side exit reconstruction tests passed.
- Fee application and take-profit ordering tests passed.
- Existing scanner, matched-control, context, baseline, upload and secret-key tests passed.

Two unchanged positive-event archive tests require PyArrow and could not be collected in the local offline build environment. PyArrow remains pinned in `requirements.txt` for GitHub Actions and Render.

## Research-integrity controls

- H1 thresholds are not dashboard-editable.
- Confirmation acceptance criteria are fixed in code and package metadata.
- The app downloads staged confirmation packages only after the protocol is frozen.
- Failed confirmation does not unlock the backtest.
- Backtest and confirmation periods cannot overlap.
- Backtest end is capped at 22 May 2026.
- Trade parameters are enforced in both the database schema and worker.
- Signals use completed bars only; entry starts in the following minute.
- Current-universe survivorship bias is reported explicitly.

## Remaining limitations

- Network calls to live Binance, Supabase and Render could not be exercised in the packaging environment.
- Historical executed trades do not reproduce unavailable historical order-book queues.
- Aggregate archive availability and job duration will vary by symbol.
- The current tradeable universe omits delisted historical assets.
