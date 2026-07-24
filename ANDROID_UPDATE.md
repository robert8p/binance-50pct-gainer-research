# Android/Termux upgrade from V6 to V7

Run `supabase/migrate_v6_to_v7.sql` in Supabase first.

Download the V7 ZIP into Android's Downloads folder, then run:

```bash
cd ~/binance-50pct-app
unzip -o ~/storage/downloads/binance_8h_50pct_fresh_confirmation_backtest_v7_0_0.zip
git add .
git commit -m "Upgrade to v7 eight-hour surge research"
git push
```

Wait for both Render services to redeploy and confirm `/health` reports version `7.0.0`.

Prior three-hour scans are retained as history but cannot be selected for V7 downstream jobs. Queue a new eight-hour scan and follow the exact sequence in `WINDOWS_UPDATE.md`; the dashboard steps are the same on Android.
