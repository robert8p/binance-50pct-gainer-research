# Deployment — V8.0.0

V8 uses the existing GitHub, Render and Supabase deployment.

1. Run `supabase/migrate_v7_to_v8.sql` in Supabase SQL Editor.
2. Upload all extracted V8 files into the existing private GitHub repository.
3. Commit the replacement files.
4. Wait for the web service and background worker to redeploy.
5. Confirm `/health` reports version `8.0.0`.
6. Run an explicit historical eight-hour scan from `2025-11-01` to `2026-01-01`.
7. Select that completed scan in Step 6 and run corrected fresh confirmation.
8. Run Step 7 only if Step 6 returns PASS.

No new secrets or Render services are required.
