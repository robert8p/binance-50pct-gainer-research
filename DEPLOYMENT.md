# V10 deployment

1. Run `supabase/migrate_v9_to_v10.sql` in the existing Supabase project.
2. Replace the existing GitHub repository contents with V10.
3. Allow the Render Blueprint services to redeploy.
4. Confirm `/health` returns version `10.0.0`.
5. Queue the fixed 180-day eight-hour scan.
6. Queue the neutral ChatGPT export from that completed scan.
7. Download the index and discovery packages; keep validation and sealed test closed.

No new Render secrets or Binance credentials are required.
