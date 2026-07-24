# V7 quality report

## Scope of the change

V7 broadens the qualifying target from a 50% rise within three hours to a 50% rise within eight hours. The change propagates through scanning, matched controls, contamination audits, baseline context, outcome diagnostics, confirmation metadata and the precursor-to-continuation arm window.

The separately frozen executable trade maximum hold remains three hours.

## Automated checks completed locally

- 45 network-free tests passed.
- Python compilation passed for every application and test module.
- V7 schema and additive-migration checks passed.
- The preregistered V7 protocol file and fresh evidence dates were tested.
- Scanner tests confirmed a qualifying crossing late in the 480-minute window.
- Scanner tests rejected a crossing outside the conservative eight-hour window.
- Matched-control tests enforced the 480-minute horizon and contamination protection.
- Baseline-context tests included the 480-minute snapshot and eight-hour target metadata.
- Confirmation and continuous-backtest protocol identifiers were tested.
- The continuation arm was tested at 480 minutes while the trade hold remained 180 minutes.
- Existing authentication, upload, checksum, restart, saleability and secret-key tests remained passing in the available suite.

Two unchanged positive-event archive tests require PyArrow and could not be collected in the local offline build environment because the dependency was unavailable from the local package index. `pyarrow==21.0.0` remains pinned in `requirements.txt` for GitHub Actions and Render.

## Research-integrity controls

- Prior three-hour scans are excluded from V7 downstream workflow selectors.
- V7 source jobs must use `v7_rolling_8h` and a 480-minute window.
- Matched controls must include the 480-minute horizon.
- Fresh V7 evidence must end on or before 1 January 2026.
- H1 thresholds are not dashboard-editable.
- Confirmation acceptance criteria are fixed in code and package metadata.
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
- Widening the target window changes the target population; all earlier three-hour conclusions must be retested rather than carried over.
