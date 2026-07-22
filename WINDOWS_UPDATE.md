# Simple Windows upgrade from v3 to v4

## 1. Download and extract

Download the v4 ZIP, right-click it in Downloads, select **Extract All**, and open the extracted folder.

## 2. Update Supabase first

1. Open the extracted `supabase` folder.
2. Open `migrate_v3_to_v4.sql` in Notepad.
3. Press `Ctrl+A`, then `Ctrl+C`.
4. In Supabase, open **SQL Editor → New query**.
5. Paste and select **Run**.
6. Confirm there is no red error.

## 3. Replace the GitHub files

1. Open the existing GitHub repository.
2. Select **Add file → Upload files**.
3. In Windows Explorer, select everything inside the extracted v4 folder.
4. Drag the selected files into GitHub.
5. Tick **Replace files with the same name** if GitHub asks.
6. Commit with: `Upgrade to v4 ten-day context`.

Uploading the folder contents preserves the required top-level `app`, `supabase`, `tests`, `render.yaml` and `requirements.txt` structure.

## 4. Wait for Render

Both services should redeploy automatically:

```text
binance-50pct-scanner-web
binance-50pct-scanner-worker
```

When both are Live, open:

```text
https://YOUR-RENDER-APP.onrender.com/health
```

Expected result:

```json
{"status":"ok","version":"4.0.0"}
```

## 5. Run the existing-data ten-day job

1. Open the main app dashboard.
2. Find **Step 4 — Build ten-day context**.
3. Select the matched-control job that produced the 63-event/301-control package.
4. Select **Existing/opened data — exploratory only**.
5. Leave `15,30,60,120` and `500` unchanged.
6. Select **Queue ten-day context package**.
7. Refresh periodically until complete.
8. Download `ten_day_context_index.zip` and `ten_day_context_exploratory.zip`.

## 6. Fresh evidence later

To create an earlier untouched round, enter both historical date fields in Step 1, then run Step 3 and Step 4 using **fresh staged** mode. Do not open validation or sealed-test downloads early.
