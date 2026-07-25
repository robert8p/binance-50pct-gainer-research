# V9 troubleshooting

## The final backtest button fails immediately

Confirm `/health` shows version `9.0.0` and that `supabase/migrate_v8_to_v9.sql` completed successfully. The most common cause is the old database constraint that only permitted a +15% take-profit.

## Database error mentioning confirmation_job_id

Run the V8-to-V9 migration. V9 deliberately stores `confirmation_job_id` as null because H1, H2 and H3 are retired.

## The job remains queued

Open the Render worker service. It must be **Live** and its logs should show `Worker started; interrupted jobs recovered`. Confirm the Supabase environment variables are populated.

## The job is very slow

V9 scans every completed minute across the canonical Binance Spot universe and downloads aggregate trades for executable candidates. A four-month run can take hours. Do not queue it twice.

## Completed with warnings

Download the result package. Warnings can come from missing historical archives or failed execution reconstruction. Formal graduation also requires at least 95% average minute coverage and no more than 5% symbol-generation failures.

## PASS appears on the dashboard

A PASS does not authorise automated or live trading. Upload the result ZIP for an independent review of the outputs and the survivorship-bias limitation.

## FAIL appears on the dashboard

Do not alter thresholds, exits or dates and rerun. The frozen research decision is to retire the OHLCV-only Binance surge programme.
