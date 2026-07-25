# V10.1 troubleshooting

## Nothing appears in the export dropdown

The dropdown only accepts a completed eight-hour scan with exactly:

- Start: `2026-01-01`
- End exclusive: `2026-07-25`

Refresh the dashboard after the scan completes and confirm `/health` shows version `10.1.0`.

## Scan rejects the date range

V10.1 expands the explicit historical-window limit to 240 days. If the app still says 180 days, Render is running an older version.

## Export appears slow

The job downloads and deduplicates ten days of one-minute history for events and controls across 205 scan days. Do not queue it twice. Check worker logs and heartbeat.

## No validation or sealed files appear

This is intentional. Earlier 2026 research means the year cannot honestly provide untouched validation. V10.1 exports 2026 as discovery only.
