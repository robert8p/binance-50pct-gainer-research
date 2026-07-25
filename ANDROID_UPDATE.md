# Android update to V9

The simplest route is still to update the existing GitHub repository through the browser or Termux.

1. Run `supabase/migrate_v8_to_v9.sql` in the Supabase SQL Editor.
2. Upload every extracted V9 file to the existing GitHub repository and replace matching files.
3. Commit as `Upgrade to v9 momentum-only backtest`.
4. Wait for both Render services to redeploy.
5. Confirm `/health` reports version `9.0.0`.
6. Queue the one frozen momentum-only backtest from the dashboard.

No precursor-confirmation job is required.
