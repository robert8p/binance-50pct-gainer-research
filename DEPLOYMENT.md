# Deployment and operating sequence

V6 uses the existing GitHub, Render and Supabase deployment. Run `supabase/migrate_v5_to_v6.sql`, upload the new source files and confirm `/health` reports version 6.0.0.

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

## Fixed V6 protocol

The recommended fresh-confirmation scan is 2026-01-01 through 2026-03-01 exclusive. The sealed continuous backtest is 2026-03-01 through 2026-05-22 exclusive.

The worker refuses to run the backtest unless:

- the linked confirmation job completed and passed;
- the backtest does not overlap the confirmation source scan;
- the end date is no later than 2026-05-22;
- all execution parameters retain their frozen values.

## Operational notes

The continuous backtest processes symbols sequentially and removes each symbol's archive cache afterwards to stay within the 10 GB disk. A worker restart requeues the job safely, but may require historical files to be downloaded again.

The dashboard does not auto-refresh. Refresh the browser to see progress.
