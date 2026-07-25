# Android update to V10

1. Download and extract the V10 ZIP using your Android file manager.
2. Run `supabase/migrate_v9_to_v10.sql` in the Supabase SQL Editor.
3. Upload all extracted files to the existing private GitHub repository, replacing matching files.
4. Wait for both Render services to redeploy.
5. Confirm `/health` reports `10.0.0`.
6. Queue the fixed 2025-01-01 to 2025-06-30 scan.
7. After completion, queue the neutral ChatGPT export once.
8. Download only the index and discovery packages initially.

A Windows browser is easier for uploading the repository and downloading the large discovery package, but the workflow can be operated from Android.
