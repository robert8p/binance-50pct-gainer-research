# Troubleshooting — V6.0.0

## Dashboard fails after upgrade

Run `supabase/migrate_v5_to_v6.sql` in Supabase. The V6 dashboard queries the new confirmation and backtest tables.

## Confirmation job fails

Confirm the source baseline-context job:

- completed successfully;
- used `fresh_staged` mode;
- contains discovery, validation and sealed packages;
- came from an explicit historical scan ending no later than 22 May 2026.

Do not use the already-opened May–July exploratory job.

## Backtest button has no selectable job

Step 7 only lists completed Step 6 jobs whose decision is **PASS**. A failed confirmation deliberately locks the backtest.

## Backtest rejects the dates

The backtest must:

- start on or after the confirmation source scan's exclusive end date;
- end no later than 22 May 2026;
- use a non-empty period.

The recommended dates are 1 March–22 May 2026 after a 1 January–1 March confirmation scan.

## Backtest is slow

This is expected. It evaluates every completed minute across the current canonical Binance Spot universe and downloads official daily archives. The worker processes symbols sequentially to control disk usage.

Do not queue a duplicate job. Refresh the dashboard manually to view progress.

## Many entry or exit fills fail

This is a research result, not necessarily a software failure. The app requires historical aggressive-side executions to prove a 500-quote-unit entry and full exit. Check `aggregate_trade_coverage.csv` to distinguish missing archives from insufficient executed liquidity.

## Worker restarts

Running jobs are automatically requeued. To keep the 10 GB disk bounded, V6 removes per-symbol cache files after processing, so a restarted long backtest may redownload some files.

## Files to share

After Step 6:

```text
fresh_confirmation_results.zip
```

After a passing Step 6 and completed Step 7:

```text
continuous_backtest_results.zip
```
