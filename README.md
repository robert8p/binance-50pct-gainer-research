# Binance ChatGPT Research Exporter — V10.0.0

V10 corrects the division of labour in this research programme.

The app is now **research infrastructure only**. It:

- scans Binance Spot for saleable coins that rose at least 50% within eight hours;
- selects fair same-coin non-event controls using the scanner's identical rolling-local-low algorithm;
- downloads ten days of raw one-minute Binance data before each event/control baseline;
- adds raw BTC, ETH and BNB reference series;
- partitions evidence chronologically into discovery, validation and sealed test;
- verifies source files and exports neutral Parquet packages.

The app does **not** choose a pattern, calculate a preferred signal, optimise thresholds or simulate a trade. ChatGPT performs those tasks from the discovery package.

## Frozen V10 evidence window

V10 is fixed to a fresh 180-day period:

- start inclusive: `2025-01-01`
- end exclusive: `2025-06-30`

This prevents the already-opened 2025–2026 research periods from being silently recycled as new evidence.

## Output files

- `CHATGPT_RESEARCH_INDEX.zip` — manifests, checksums, exclusions and split counts.
- `DISCOVERY_UPLOAD_TO_CHATGPT.zip` — raw labelled discovery evidence; upload this to ChatGPT.
- `VALIDATION_DO_NOT_OPEN.zip` — keep closed until ChatGPT freezes candidate rules and acceptance criteria.
- `SEALED_TEST_DO_NOT_OPEN.zip` — keep closed until a final rule survives validation without retuning.

Each evidence package contains:

- `samples.csv` — labels and sample metadata;
- `minute_data/*.parquet` — deduplicated raw one-minute symbol histories covering every sample window;
- `reference_data/*.parquet` — raw BTCUSDT, ETHUSDT and BNBUSDT data;
- `analysis_loader.py` — a neutral sample-window loader;
- `DATA_DICTIONARY.md` and split metadata.

## Research integrity

Events and controls use the same local-low selection algorithm. Controls are rejected if they contain a future 50% eight-hour rise, occur near another known event, lack complete history or reuse a control baseline.

The exact contract is in `docs/V10_RESEARCH_EXPORT_PROTOCOL.json`.

## Deployment

Existing users should run `supabase/migrate_v9_to_v10.sql`, upload the V10 repository files and wait for both Render services to redeploy.

After `/health` shows version `10.0.0`:

1. Queue the fixed 2025-01-01 to 2025-06-30 eight-hour scan.
2. Select that completed scan under the neutral ChatGPT export section.
3. Queue the export once.
4. Download the index and discovery packages only.
5. Upload those two packages to ChatGPT for blank-canvas pattern analysis.
