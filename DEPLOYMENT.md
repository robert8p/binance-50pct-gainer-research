# Deployment — v4.0.0

## Existing v3 installation

1. In Supabase, open **SQL Editor**.
2. Paste and run `supabase/migrate_v3_to_v4.sql`.
3. Upload all v4 files to the existing GitHub repository, replacing files with the same names.
4. Commit the changes.
5. Wait for both Render services to redeploy.
6. Open `/health`; confirm `{"status":"ok","version":"4.0.0"}`.
7. Confirm the dashboard shows a recent worker heartbeat and **Step 4 — Build ten-day context**.

Do not deploy the v4 web service before running the migration: the dashboard queries the new context tables at startup.

## Existing 63-event dataset

Choose the completed matched-control job and select:

```text
Research treatment: Existing/opened data — exploratory only
Context history: 10 days
Decision horizons: 15,30,60,120
Minimum 5-minute quote volume: 500
```

Download `ten_day_context_index.zip` and `ten_day_context_exploratory.zip` after completion.

## Fresh earlier historical round

1. Queue a scan with both historical date fields populated.
2. Keep threshold 50%, rolling window three hours and saleability 500/300 seconds.
3. Build five matched controls per event.
4. Build ten-day context and choose **New untouched data — staged discovery/validation/sealed**.
5. Download the index and discovery package only.

A fixed-date scan can cover 1–180 completed UTC days. The end date is exclusive.
