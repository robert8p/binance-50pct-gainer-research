# Deployment — v5.0.0

## Existing v4 installation

1. In Supabase, run `supabase/migrate_v4_to_v5.sql`.
2. Upload all v5 files to the existing GitHub repository, replacing files with the same names.
3. Commit the changes.
4. Wait for both Render services to redeploy.
5. Open `/health`; confirm `{"status":"ok","version":"5.0.0"}`.
6. Confirm the dashboard shows a recent worker heartbeat and **Step 5 — Build baseline-aligned context**.

Do not deploy the v5 web service before running the migration: the dashboard queries the new baseline-context tables at startup.

## Existing 63-event dataset

Choose the completed matched-control job and select:

```text
Research treatment: Existing May–July data — exploratory alignment audit
Minimum 5-minute quote volume: 500
```

Download `baseline_context_index.zip` and `baseline_context_exploratory.zip` after completion.

## Fresh earlier historical round

1. Queue an explicit historical scan ending no later than 22 May 2026.
2. Keep threshold 50%, rolling window three hours and saleability 500/300 seconds.
3. Build five matched controls per event with horizons `15,30,60,120,180`.
4. Queue Step 5 and choose **Earlier untouched data — discovery/validation/sealed**.
5. Download the index and discovery package only.

Fresh staged mode rejects a matched-control job without 180-minute pre-anchor contamination protection or a scan that overlaps the already opened May–July observations.
