# Binance ChatGPT Research Exporter — V10.1.0

V10.1 runs the neutral ChatGPT research export over **2026 year to date**.

The app is research infrastructure only. It:

- scans Binance Spot for saleable coins that rose at least 50% within eight hours;
- selects same-coin non-event controls using the scanner's identical rolling-local-low algorithm;
- downloads ten days of raw one-minute Binance data before each event/control baseline;
- adds raw BTC, ETH and BNB reference series;
- exports neutral, deduplicated Parquet evidence for ChatGPT.

The app does **not** choose a pattern, rank a feature, optimise thresholds, fit a model or simulate a trade.

## Frozen 2026 window

- Start inclusive: `2026-01-01`
- End exclusive: `2026-07-25`
- Latest included UTC day: `2026-07-24`
- Total: 205 completed UTC days

## Research-integrity treatment

Parts of 2026 were already examined during earlier rounds. V10.1 therefore treats **all 2026 data as exploratory discovery evidence**. It deliberately does not create validation or sealed-test files from 2026.

After ChatGPT completes blank-canvas discovery and freezes candidate rules, separate earlier periods will be collected for validation and sealed testing.

## Output files

- `CHATGPT_RESEARCH_INDEX.zip` — manifests, checksums, exclusions and counts.
- `DISCOVERY_2026_UPLOAD_TO_CHATGPT.zip` — raw labelled 2026 discovery evidence.

Each evidence package contains `samples.csv`, deduplicated `minute_data/*.parquet`, raw BTC/ETH/BNB reference data, a neutral loader and a data dictionary.

## Deployment

If V10 tables already exist, no new Supabase migration is needed. Upload the V10.1 files and wait for both Render services to redeploy.

If upgrading directly from V9 or earlier, run `supabase/migrate_v9_to_v10.sql` first.

After `/health` shows `10.1.0`:

1. Queue the fixed 2026-01-01 to 2026-07-25 eight-hour scan.
2. Select that completed scan under the neutral ChatGPT export section.
3. Queue the export once.
4. Download the index and 2026 discovery packages.
5. Upload both to ChatGPT for blank-canvas analysis.

The exact contract is in `docs/V10_2026_DISCOVERY_PROTOCOL.json`.
