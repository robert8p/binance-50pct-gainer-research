# Simple Windows upgrade and run guide — V8

## A. Upgrade the existing app

### 1. Download and extract

Download and extract:

```text
binance_8h_50pct_local_low_confirmation_v8_0_0.zip
```

### 2. Update Supabase

1. Open the extracted folder.
2. Open `supabase\migrate_v7_to_v8.sql` in Notepad.
3. Press `Ctrl+A`, then `Ctrl+C`.
4. Open your existing Supabase project.
5. Open **SQL Editor → New query**.
6. Paste the SQL and select **Run**.

The migration preserves all existing scans and research packages.

### 3. Replace the GitHub files

1. Open the existing private GitHub repository.
2. Select **Add file → Upload files**.
3. Drag everything from inside the extracted V8 folder onto the page.
4. Confirm the top level still contains `app`, `supabase`, `tests`, `render.yaml` and `requirements.txt`.
5. Commit with:

```text
Upgrade to v8 local-low confirmation
```

### 4. Confirm Render

Wait until both services are **Live**, then open:

```text
https://YOUR-APP.onrender.com/health
```

Expected result:

```json
{"status":"ok","version":"8.0.0"}
```

## B. Run the untouched V8 confirmation

### 5. Queue the fresh eight-hour scan

In Step 1 use:

```text
Historical start:       2025-11-01
Historical end:         2026-01-01
Threshold:              50
Rolling window:         8 hours
Minimum exit notional:  500
Saleability window:     300 seconds
```

Queue the scan and wait for `completed` or `completed_with_warnings`.

You do not need to run Steps 2–5 for this confirmation round.

### 6. Run Step 6

In **Step 6 — Confirm H3 with algorithmic local-low controls**:

1. Select the completed `2025-11-01` to `2026-01-01` scan.
2. Leave controls per event at `5`.
3. Leave history at `10` days.
4. Leave liquidity at `500`.
5. Select **Run corrected fresh confirmation**.

The worker will:

- calculate H3 at each genuine event baseline;
- build controls using the same rolling-minimum baseline algorithm;
- reject contaminated controls;
- test discovery, validation and sealed chronological segments;
- report results by event-duration band.

Refresh the dashboard periodically. Do not queue the job twice.

### 7. Share the result

When complete, download:

```text
fresh_confirmation_results.zip
```

Upload that ZIP for analysis.

### 8. Step 7 only after PASS

If Step 6 says **FAIL**, stop. Do not alter the 0.4 or +5% thresholds and rerun while calling it confirmation.

If Step 6 says **PASS**, Step 7 becomes available. Use:

```text
Backtest start:          2026-01-01
Backtest end exclusive:  2026-05-22
```

The frozen trade remains 500 quote units, +15% take profit, −5% stop loss, three-hour maximum hold, 0.10% fee each side and no more than five filled entries per UTC day.
