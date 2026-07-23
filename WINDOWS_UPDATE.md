# Simple Windows upgrade to V6

## 1. Update Supabase

1. Extract the V6 ZIP.
2. Open `supabase\migrate_v5_to_v6.sql` in Notepad.
3. Press `Ctrl+A`, then `Ctrl+C`.
4. Open **Supabase → SQL Editor → New query**.
5. Paste and select **Run**.

The migration is additive and keeps all prior scans and research packages.

## 2. Update GitHub

1. Open the existing GitHub repository.
2. Select **Add file → Upload files**.
3. Drag everything from inside the extracted V6 folder onto the upload page.
4. Confirm replacement when GitHub shows existing files.
5. Commit with:

```text
Upgrade to v6 fresh confirmation and continuous backtest
```

## 3. Check Render

Wait for both services to redeploy:

```text
binance-50pct-scanner-web
binance-50pct-scanner-worker
```

Open:

```text
https://YOUR-RENDER-APP.onrender.com/health
```

Expected result:

```json
{"status":"ok","version":"6.0.0"}
```

## 4. Run the fresh confirmation dataset

### Step 1 — Fresh scan

Queue a scan with:

```text
Historical start: 2026-01-01
Historical end, exclusive: 2026-03-01
Threshold: 50
Rolling window: 3 hours
Minimum exit notional: 500
Saleability window: 300 seconds
```

### Step 3 — Matched controls

After the scan completes, queue matched controls with:

```text
Controls per event: 5
Predictor-history days: 10
Decision horizons: 15,30,60,120,180
Minimum prior five-minute quote volume: 500
```

The `180` horizon is mandatory for contamination protection.

### Step 5 — Baseline context

After matched controls complete:

```text
Research treatment: Earlier untouched data — discovery/validation/sealed
Minimum prior five-minute quote volume: 500
```

### Step 6 — Automatic confirmation

Select the completed fresh baseline-context job and choose:

```text
Run automatic fresh confirmation
```

Do not manually download or inspect its discovery, validation or sealed files first.

## 5. Interpret Step 6

- **PASS:** Step 7 becomes available.
- **FAIL:** Stop. Do not change H1 thresholds and rerun while calling it confirmation.

Download `fresh_confirmation_results.zip` and upload it to ChatGPT.

## 6. Run the sealed continuous backtest only after PASS

Use:

```text
Start: 2026-03-01
End, exclusive: 2026-05-22
Quote preference: USDT,USDC,FDUSD
```

All trading parameters are fixed automatically.

The job can take many hours because it evaluates every completed minute across the current Binance Spot universe and downloads official aggregate-trade archives for candidate signals.

After completion, download and upload:

```text
continuous_backtest_results.zip
```
