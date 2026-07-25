# V10 troubleshooting

## No scan appears in the neutral exporter dropdown

The dropdown only accepts a completed eight-hour scan with the exact explicit window:

- `2025-01-01`
- `2025-06-30` exclusive

Refresh the dashboard after the scan reaches `completed` or `completed_with_warnings`.

## Export remains queued

Open the Render background worker and confirm it is **Live**. Its logs should show `Worker started; interrupted jobs recovered`. Verify that the worker has the same `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` as the web service.

## Export is slow

The app is downloading and packaging ten days of one-minute data for every event and five matched controls, plus market references. It uses monthly Binance archives for complete months, but the job can still take hours. Do not queue duplicates.

## `pyarrow` or Parquet error

Render must install the pinned `pyarrow==21.0.0` dependency from `requirements.txt`. Trigger **Clear build cache & deploy** if an old environment was reused.

## One coin fails because its symbol contains non-Latin characters

V10 converts storage filenames to deterministic ASCII-safe names while retaining the original Binance symbol inside `samples.csv`. This fixes the earlier Supabase path issue.

## Validation or sealed package was opened accidentally

Treat that partition as contaminated. Do not claim it as untouched evidence. A different historical period will be required for a defensible final test.
