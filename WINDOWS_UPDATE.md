# Simple Windows upgrade from v4 to v5

## 1. Download and extract

Download the v5 ZIP, right-click it in **Downloads**, select **Extract All**, and open the extracted folder.

## 2. Update Supabase first

1. Open the extracted `supabase` folder.
2. Open `migrate_v4_to_v5.sql` in Notepad.
3. Press `Ctrl+A`, then `Ctrl+C`.
4. In Supabase, open **SQL Editor → New query**.
5. Paste and select **Run**.
6. Confirm there is no red error.

This migration is additive and does not remove your existing scans or packages.

## 3. Replace the GitHub files

1. Open the existing GitHub repository.
2. Select **Add file → Upload files**.
3. In Windows Explorer, select everything inside the extracted v5 folder.
4. Drag the selected files into GitHub.
5. Tick **Replace files with the same name** if GitHub asks.
6. Commit with:

```text
Upgrade to v5 baseline-aligned context
```

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
{"status":"ok","version":"5.0.0"}
```

## 5. Run the existing-data alignment audit

1. Open the main app dashboard.
2. Find **Step 5 — Build baseline-aligned context**.
3. Select the matched-control job that produced the 63-event/301-control package.
4. Select **Existing May–July data — exploratory alignment audit**.
5. Leave the minimum five-minute quote volume at `500`.
6. Select **Queue baseline-aligned package**.
7. Refresh periodically until complete.
8. Download:

```text
baseline_context_index.zip
baseline_context_exploratory.zip
```

Share both files for analysis.

## 6. Create the fresh earlier round after the audit

Use these fixed historical dates in Step 1:

```text
Start date: 2026-01-01
End date exclusive: 2026-05-22
```

Then:

1. Run the 50%/three-hour scan.
2. Build five matched controls per event.
3. Keep the Step 3 horizons as `15,30,60,120,180`.
4. In Step 5 select the new matched-control job.
5. Choose **Earlier untouched data — discovery/validation/sealed**.
6. Download the index and **discovery** package only.
7. Do not open validation or sealed test until instructed.
