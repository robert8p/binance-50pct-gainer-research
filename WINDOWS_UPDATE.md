# Simple Windows upgrade steps

1. Download and extract the V12 deployment ZIP.
2. Open your existing GitHub repository in the browser.
3. Replace the existing repository files with the files inside the extracted V12 folder.
4. Commit with the message:

   `Deploy V12 exact entry validation`

5. Open Supabase → SQL Editor → New query.
6. Open `supabase/migrate_v10_to_v12.sql` from the extracted folder, copy all of it into Supabase, and press **Run** once.
7. Open Render and confirm both the web service and worker redeploy.
8. Visit the web-service `/health` page. It must show:

   `{"status":"ok","version":"12.0.0"}`

9. Open the dashboard and press **Queue V12 validation** once.
10. Keep the worker running until the job completes, then download `ENTRY_VALIDATION_2025_RESULTS.zip`.

The job uses 1 January through 30 June 2025 only. It does not open the reserved July–October sealed period.
