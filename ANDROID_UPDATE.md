# Android upgrade from v2 to v3

## 1. Apply the database migration

Open `supabase/migrate_v2_to_v3.sql` from the extracted package, copy all text, paste it into the existing Supabase project's SQL Editor and run it.

## 2. Replace local files

```bash
cd ~/binance-50pct-app
unzip -o ~/storage/downloads/binance_3h_50pct_matched_controls_v3_0_0.zip
```

## 3. Commit and push

```bash
git add .
git commit -m "Upgrade Binance matched-control research app to v3"
git push origin main
```

## 4. Verify Render

Wait for both services to show **Live**, then open `/health` and confirm:

```json
{"status":"ok","version":"3.0.0"}
```

No new Render secrets are required.

## 5. Queue controls

Use the existing completed 63-event scan with five controls per event, ten prior days and horizons `15,30,60,120`.
