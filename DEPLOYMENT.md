# Deployment — v2.0.0

## Existing v1.x installation

Use `ANDROID_UPDATE.md`. Version 2 keeps the same Render service names and Supabase tables, so it upgrades the existing deployment rather than creating a second app.

Use `supabase/migrate_v1_to_v2.sql` for an existing v1 database. The migration is additive, preserves prior data and leaves v1 scan-version fields null so old scans cannot be mistaken for v2 scans.

## Fresh installation

1. Create a Supabase project.
2. Run the complete `supabase/schema.sql` in SQL Editor.
3. Confirm the `binance_` tables and private `binance-gainer-research` Storage bucket exist.
4. Upload the repository to a private GitHub repository.
5. Create a Render Blueprint from root-level `render.yaml`.
6. Supply `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `APP_PASSWORD` to both services.
7. Wait for the web and worker services to show **Live**.
8. Open `/health`; the response should be:

```json
{"status":"ok","version":"2.0.0"}
```

9. Open the dashboard and confirm a recent worker heartbeat.
10. Queue the first scan with the displayed defaults:

```text
Lookback: 60 completed UTC days
Threshold: 50%
Rolling window: fixed at 3 hours
Quote preference: USDT,USDC,FDUSD
Minimum saleability turnover: 500 quote units
Saleability window: 300 seconds
```

The **Saleable** count is the primary result. The **3h candidates** count includes audit failures.

After discovery, run one research event before setting maximum events to `0` for all saleable events.
