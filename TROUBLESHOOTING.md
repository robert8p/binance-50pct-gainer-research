# Troubleshooting — v2.0.0

## Render reports a missing database column

Run the complete updated `supabase/schema.sql` in Supabase SQL Editor. Version 2 adds `window_minutes`, `candidates_found`, rolling-baseline fields and new saleability metrics.

## Candidates exist but Saleable is zero

Download **all candidates** and inspect:

- `baseline_trade_unresolved`;
- `crossing_trade_unresolved`;
- `exact_window_pass`;
- `seller_taker_notional_any_price`;
- `minimum_exit_notional`;
- `sellability_trades_truncated`;
- `minimum_exit_vwap_pct_vs_threshold`.

A coin may touch +50%, fall immediately and still pass if enough seller-initiated turnover occurs at lower prices. Conversely, a high print with little executable turnover fails.

## Candidate count is lower than expected

The app deliberately excludes:

- same-minute low-to-high moves;
- exact baseline-to-crossing intervals above three hours;
- second or later events for the same pair on the same UTC day;
- delisted coins absent from the current exchange universe.

## Scan takes longer than v1

Rolling-window validation fetches up to 27 hours of minute bars for each shortlisted day and resolves both baseline and crossing trades. The daily prefilter limits this work, but a volatile period can produce more candidate days.

## Health is live but no worker heartbeat appears

Check the Render worker logs and verify that both services have identical values for:

- `SUPABASE_URL`;
- `SUPABASE_SERVICE_ROLE_KEY`;
- `APP_PASSWORD`.

## Old dashboard still shows 90 days

Render is serving an older commit. Confirm GitHub contains version 2 files, then manually deploy the latest commit on both Render services.
