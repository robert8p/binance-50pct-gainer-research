# V10.1 deployment

1. If V10 tables do not yet exist, run `supabase/migrate_v9_to_v10.sql`.
2. Upload the repository files to GitHub.
3. Wait for both Render services to redeploy.
4. Confirm `/health` returns version `10.1.0`.
5. Queue the fixed 2026-01-01 to 2026-07-25 scan.
6. Queue the neutral export from that completed scan.
7. Upload the index and `DISCOVERY_2026_UPLOAD_TO_CHATGPT.zip` to ChatGPT.

All 2026 evidence is exploratory discovery-only.
