# Android/Termux upgrade from v3 to v4

Run the Supabase migration first, then replace your local repository files with the extracted v4 package and push:

```bash
cd ~/binance-50pct-app
unzip -o ~/storage/downloads/binance_3h_50pct_ten_day_context_v4_0_0.zip
git add .
git commit -m "Upgrade to v4 ten-day context"
git push
```

Wait for both Render services to redeploy and confirm `/health` reports version 4.0.0.
