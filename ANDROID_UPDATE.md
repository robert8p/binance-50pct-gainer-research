# Android/Termux upgrade from v4 to v5

Run the Supabase migration first, then replace your local repository files with the extracted v5 package and push:

```bash
cd ~/binance-50pct-app
unzip -o ~/storage/downloads/binance_3h_50pct_baseline_context_v5_0_0.zip
git add .
git commit -m "Upgrade to v5 baseline-aligned context"
git push
```

Wait for both Render services to redeploy and confirm `/health` reports version 5.0.0.
