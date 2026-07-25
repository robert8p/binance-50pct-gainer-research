# Simple Windows upgrade to V9

## 1. Download and extract

Download `binance_momentum_continuation_backtest_v9_0_0.zip` and select **Extract All**.

## 2. Update Supabase first

1. Open the extracted folder.
2. Open `supabase\migrate_v8_to_v9.sql` in Notepad.
3. Press `Ctrl+A`, then `Ctrl+C`.
4. Open your existing Supabase project.
5. Open **SQL Editor → New query**.
6. Paste the SQL and select **Run**.

The migration preserves all previous scans and results. It allows V9 backtests to run without a precursor-confirmation job and permits the frozen +10% target.

## 3. Replace the GitHub files

1. Open your existing GitHub repository.
2. Select **Add file → Upload files**.
3. Drag everything from inside the extracted V9 folder onto GitHub.
4. Allow files with the same names to be replaced.
5. Commit with:

`Upgrade to v9 momentum-only backtest`

## 4. Wait for Render

Wait for both the web service and worker to redeploy.

Open:

`https://YOUR-APP.onrender.com/health`

Expected response:

`{"status":"ok","version":"9.0.0"}`

## 5. Run the final backtest

On the dashboard, find **Final test — Run frozen momentum-only backtest**.

The historical dates are locked to:

- Start: `2025-07-01`
- End, exclusive: `2025-11-01`

Leave the quote preference as:

`USDT,USDC,FDUSD`

Select **Queue final continuous backtest** once.

You do not need to run Steps 1–6. V9 does not use an event scan, matched controls or a precursor confirmation.

## 6. Download the result

When the job is complete, download:

`continuous_backtest_results.zip`

Upload that ZIP to ChatGPT for the final assessment. Do not queue a second run or change any parameter after seeing the outcome.
