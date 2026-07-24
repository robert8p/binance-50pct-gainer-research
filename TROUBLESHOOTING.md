# Troubleshooting — V8.0.0

## Step 6 dropdown is empty

Step 6 only lists completed eight-hour scans with an explicit end date no later than `2026-01-01`.

Run a new Step 1 scan using:

```text
2025-11-01 to 2026-01-01
```

Then refresh the dashboard.

## Confirmation remains queued

Open Render and confirm `binance-50pct-scanner-worker` is Live. Check its latest logs and verify the Supabase environment variables are populated.

## Few controls were created

V8 deliberately rejects controls that:

- lack complete ten-day history;
- lack 500 quote units of pre-baseline liquidity;
- sit near a known event;
- fall into a different duration band;
- or rise 50% within eight hours after the selected local-low baseline.

The output package contains `control_rejections.csv` for diagnosis.

## Confirmation fails

Stop. Do not change H3 thresholds using the fresh result. The failed result is evidence that the exploratory pattern did not generalise adequately.

## Backtest dropdown is empty

Step 7 is intentionally locked unless a V8 Step 6 job completes with PASS.
