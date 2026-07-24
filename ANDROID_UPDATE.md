# Android update — V8

Download the V8 ZIP into Android Downloads, then in Termux:

```bash
cd ~/binance-50pct-app
unzip -o ~/storage/downloads/binance_8h_50pct_local_low_confirmation_v8_0_0.zip
git add .
git commit -m "Upgrade to v8 local-low confirmation"
git push
```

Before pushing, run `supabase/migrate_v7_to_v8.sql` in the Supabase SQL Editor.

Wait for both Render services to redeploy and confirm `/health` reports `8.0.0`.

For the fresh scan use `2025-11-01` to `2026-01-01`, then run Step 6 directly. Steps 2–5 are not required for V8 confirmation.
