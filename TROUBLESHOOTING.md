# Troubleshooting — v4.0.0

## Dashboard fails immediately after upgrade

Run `supabase/migrate_v3_to_v4.sql`. The v4 dashboard requires the new context tables.

## Context job remains queued

Open the Render worker logs. Confirm the worker is Live and both Supabase variables are populated. Restart the worker; queued jobs are preserved.

## Context job has many insufficient-history warnings

The symbol may have been newly listed or the archive may be incomplete. Do not impute missing minutes. Keep these rows flagged or analyse new listings separately.

## Historical scan rejects the dates

Both dates are required. The start is inclusive, the end is exclusive, the span must be 1–180 days, and the end cannot include a future UTC day.

## Job is slow

The ten-day job downloads and verifies one-minute archives for every event/control symbol plus BTC, ETH and BNB. The persistent cache makes subsequent runs faster. Do not queue duplicate jobs.

## Which files should be shared for analysis?

For the existing dataset, share:

```text
ten_day_context_index.zip
ten_day_context_exploratory.zip
```

For a fresh staged round, share the index and discovery package first. Keep validation and sealed test unopened.
