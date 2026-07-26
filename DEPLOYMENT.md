# V12 deployment

1. Suspend the Render worker so no older job is running during the upgrade.
2. Replace the GitHub repository contents with the files from this ZIP.
3. In Supabase SQL Editor, run `supabase/migrate_v10_to_v12.sql` once.
4. Commit and push the repository changes.
5. Resume the Render worker and wait for both services to deploy.
6. Open `/health` and confirm it returns version `12.0.0`.
7. Open the dashboard and press **Queue V12 validation** once.
8. Leave the worker running. The exact aggregate-trade stage can take many hours.
9. When complete, download `ENTRY_VALIDATION_2025_RESULTS.zip` and upload it to ChatGPT.

Do not queue a second validation job and do not access the July–October 2025 sealed period.
