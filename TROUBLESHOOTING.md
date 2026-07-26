# Troubleshooting — V11

## No scan appears in the export dropdown

The source must be a completed V11 scan with:

- event definition `v11_rolling_8h_25pct`;
- threshold 25%;
- window 480 minutes;
- dates 2026-01-01 to 2026-07-25 exclusive.

Old 50% scans are deliberately excluded. Refresh the dashboard after the V11 scan completes.

## Export is much larger or slower

A 25% threshold creates more positive events and controls than a 50% threshold. This is expected. The exporter deduplicates overlapping minute history by symbol and splits the result into upload-sized parts.

## Cancel an export

Use the dashboard Cancel button. The worker stops cooperatively after its current symbol operation.
