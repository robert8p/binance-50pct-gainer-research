# Deployment — v3.0.0

## Existing v2 installation

1. Run `supabase/migrate_v2_to_v3.sql` in the existing Supabase project's SQL Editor.
2. Replace the GitHub repository files with the v3 package and commit to `main`.
3. Wait for both existing Render services to redeploy.
4. Open `/health` and confirm:

```json
{"status":"ok","version":"3.0.0"}
```

5. Open the dashboard and confirm **Step 3 — Build matched controls** is visible.

The migration is additive. Existing scans, 63 events and positive-event research files are preserved. Do not rerun the discovery scan merely to create controls.

## Fresh installation

1. Create a Supabase project.
2. Run the complete `supabase/schema.sql` in SQL Editor.
3. Confirm the `binance_` tables and private `binance-gainer-research` bucket exist.
4. Upload the repository to a private GitHub repository.
5. Create a Render Blueprint using root-level `render.yaml`.
6. Supply these variables to both services:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
APP_PASSWORD
```

7. Wait for the web and worker services to show **Live**.
8. Confirm `/health` reports v3.0.0 and the dashboard shows a recent worker heartbeat.

## Run the current matched-control round

Use the completed 60-day scan containing 63 saleable events.

Recommended settings:

```text
Controls per event: 5
Predictor-history days: 10
Decision horizons: 15,30,60,120
Minimum prior 5-minute quote volume: 500
```

Queue the job once. The target is approximately 315 controls and 1,512 feature rows:

```text
(63 events + 315 controls) × 4 decision horizons
```

The worker downloads and verifies official one-minute archives. The first run may take materially longer than the original index generation. Closing the browser does not stop the worker.

## Download order

1. Download `matched_control_index.zip` and share it for a quality review.
2. Download and analyse `matched_control_discovery.zip`.
3. Keep validation unopened until candidate rules and thresholds have been fixed.
4. Keep sealed test unopened until validation has completed and the final rule is preregistered.
