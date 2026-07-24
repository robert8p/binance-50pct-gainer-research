# Deployment and operating sequence

V7 uses the existing GitHub, Render and Supabase deployment. Run `supabase/migrate_v6_to_v7.sql`, upload the new source files and confirm `/health` reports version `7.0.0`.

## Required services

- Render web service: dashboard
- Render Starter worker: historical processing
- Render 10 GB persistent disk: temporary verified archives
- Supabase Postgres and private Storage bucket

## Required environment variables

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
APP_PASSWORD
SUPABASE_STORAGE_BUCKET=binance-gainer-research
TEMP_DATA_DIR=/var/data
BINANCE_API_BASE_URLS=https://api.binance.com,https://data-api.binance.vision
POLL_SECONDS=10
```

Use a Supabase server-side `sb_secret_...` key or a legacy service-role JWT. Never place it in GitHub.

## Fixed V7 protocol

The target event is a rise of at least 50% from a prior-minute low to a later-minute high within 480 minutes. The price does not need to remain above the threshold.

The recommended fresh-confirmation scan is **2025-11-01 through 2026-01-01 exclusive**. The sealed continuous backtest is **2026-03-01 through 2026-05-22 exclusive**.

The worker refuses to run the backtest unless:

- the linked V7 confirmation job completed and passed;
- the backtest does not overlap the confirmation source scan;
- the end date is no later than 2026-05-22;
- all execution parameters retain their frozen values.

The eight-hour change applies to the target event, matched-control protection, context analysis and precursor-to-continuation arm window. The independently frozen trade maximum hold remains three hours.

## Operational sequence

1. Queue a new V7 eight-hour scan.
2. Build V7 matched controls containing the mandatory 480-minute horizon.
3. Build baseline context in exploratory or fresh-staged mode as appropriate.
4. Run automatic confirmation only on untouched fresh-staged data.
5. Run the continuous backtest only after confirmation passes.

Prior three-hour jobs remain stored but are excluded from V7 selectors.

## Operational notes

The continuous backtest processes symbols sequentially and removes each symbol's archive cache afterwards to stay within the 10 GB disk. A worker restart requeues the job safely, but may require historical files to be downloaded again.

The dashboard does not auto-refresh. Refresh the browser to see progress.
