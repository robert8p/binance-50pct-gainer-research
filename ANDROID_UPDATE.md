# Android/Termux upgrade from V5 to V6

Run `supabase/migrate_v5_to_v6.sql` in Supabase first.

Download the V6 ZIP, then run:

```bash
cd ~/binance-50pct-app
unzip -o ~/storage/downloads/binance_3h_50pct_fresh_confirmation_backtest_v6_0_0.zip
git add .
git commit -m "Upgrade to v6 fresh confirmation and continuous backtest"
git push
```

Wait for both Render services to redeploy and confirm `/health` reports version 6.0.0.

Use the exact research sequence in `WINDOWS_UPDATE.md`; the dashboard steps are the same on Android.
