# Simple Windows upgrade from v2 to v3

These steps update the existing app and preserve the completed scan and research data.

## 1. Apply the Supabase migration first

1. Extract the v3 ZIP in Windows.
2. Open `supabase\migrate_v2_to_v3.sql` in Notepad.
3. Press `Ctrl+A`, then `Ctrl+C`.
4. Open the existing Supabase project.
5. Open **SQL Editor → New query**.
6. Paste the SQL and select **Run**.
7. Confirm there is no red error.

Doing the database migration first prevents the newly deployed dashboard from looking for tables that do not yet exist.

## 2. Replace the GitHub files

1. Open the existing private GitHub repository.
2. Select **Add file → Upload files**.
3. Open the extracted v3 folder in File Explorer.
4. Select everything inside the folder and drag it onto the GitHub upload page.
5. Use this commit message:

```text
Upgrade Binance matched-control research app to v3
```

6. Select **Commit changes**.

Do not upload only the ZIP file. The repository root must still show `app`, `supabase`, `tests`, `render.yaml` and `requirements.txt`.

## 3. Let Render redeploy

The existing Blueprint should redeploy both services automatically.

Wait for:

```text
binance-50pct-scanner-web — Live
binance-50pct-scanner-worker — Live
```

No new environment variables are required.

## 4. Verify

Open:

```text
https://YOUR-RENDER-URL.onrender.com/health
```

Expected response:

```json
{"status":"ok","version":"3.0.0"}
```

Then open the dashboard and confirm **Step 3 — Build matched controls** appears.

## 5. Queue the matched-control job

Choose the completed scan showing 63 saleable events and use:

```text
Controls per event: 5
Predictor-history days: 10
Decision horizons: 15,30,60,120
Minimum prior 5-minute quote volume: 500
```

Select **Queue matched-control package** once.

The first run downloads a large number of official one-minute daily archives. Leave the Render worker running; the browser and computer may be closed.
