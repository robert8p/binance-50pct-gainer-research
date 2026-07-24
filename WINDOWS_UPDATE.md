# Simple Windows upgrade to V7

## 1. Extract the package

1. Download and extract `binance_8h_50pct_fresh_confirmation_backtest_v7_0_0.zip`.
2. Open the extracted folder and confirm that `app`, `supabase`, `tests`, `render.yaml` and `requirements.txt` are directly inside it.

## 2. Update Supabase

1. Open `supabase\migrate_v6_to_v7.sql` in Notepad.
2. Press `Ctrl+A`, then `Ctrl+C`.
3. Open **Supabase → SQL Editor → New query**.
4. Paste and select **Run**.

The migration is additive. It keeps all prior scans and research packages, while changing V7 defaults to the eight-hour event definition.

## 3. Update GitHub

1. Open the existing GitHub repository.
2. Select **Add file → Upload files**.
3. Drag everything from inside the extracted V7 folder onto the upload page.
4. Confirm replacement when GitHub shows existing files.
5. Commit with:

```text
Upgrade to v7 eight-hour surge research
```

## 4. Check Render

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
{"status":"ok","version":"7.0.0"}
```

## 5. Run a new eight-hour discovery scan

Do not reuse a three-hour scan. V7 deliberately excludes old three-hour jobs from the downstream dropdowns.

For a current scan, leave the historical dates blank and use:

```text
Lookback: 60 completed UTC days
Threshold: 50
Rolling window: 8 hours
Minimum exit notional: 500
Saleability window: 300 seconds
```

For fresh historical confirmation, use this untouched V7 window instead:

```text
Historical start: 2025-11-01
Historical end, exclusive: 2026-01-01
Threshold: 50
Rolling window: 8 hours
Minimum exit notional: 500
Saleability window: 300 seconds
```

## 6. Build matched controls

After the chosen V7 scan completes, queue matched controls with:

```text
Controls per event: 5
Predictor-history days: 10
Decision horizons: 15,30,60,120,180,480
Minimum prior five-minute quote volume: 500
```

The `480` horizon is mandatory for eight-hour contamination protection.

## 7. Build baseline-aligned context

After matched controls complete:

```text
Research treatment: Earlier untouched data — discovery/validation/sealed
Minimum prior five-minute quote volume: 500
```

Use this mode only for the 1 November 2025–1 January 2026 fresh scan. Use exploratory mode for any already-opened period.

## 8. Run automatic confirmation

Select the completed fresh staged baseline-context job and choose:

```text
Run automatic fresh confirmation
```

Do not manually download or inspect its discovery, validation or sealed files first.

Interpret the result as follows:

- **PASS:** Step 7 becomes available.
- **FAIL:** Stop. Do not alter H1 thresholds and rerun while describing it as confirmation.

Download `fresh_confirmation_results.zip` and upload it to ChatGPT.

## 9. Run the sealed continuous backtest only after PASS

Use:

```text
Start: 2026-03-01
End, exclusive: 2026-05-22
Quote preference: USDT,USDC,FDUSD
```

The eight-hour target and arm window are fixed automatically. The trade itself retains its separately frozen three-hour maximum hold.

The job can take many hours because it evaluates every completed minute across the current Binance Spot universe and downloads official aggregate-trade archives for candidate signals.

After completion, download and upload:

```text
continuous_backtest_results.zip
```
