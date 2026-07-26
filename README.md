# Binance 25% ChatGPT Research Exporter — V11.0.0

V11 changes the research outcome to a **saleable Binance Spot coin rising at least 25% from the selected local-low baseline within eight hours**. The coin only needs to touch +25%; it does not need to remain there.

The application stays neutral: it collects, labels, audits and packages raw evidence. ChatGPT performs feature generation and blank-canvas pattern discovery.

## Fixed discovery window

- Start: 2026-01-01 inclusive
- End: 2026-07-25 exclusive
- Window: 480 minutes
- Threshold: 25%
- Saleability: at least 500 quote units of seller-initiated executed notional within five minutes after the exact crossing
- Treatment: all 2026 evidence is exploratory discovery only

## Evidence populations

1. Every saleable 25% event with ten days of raw one-minute history.
2. Up to five same-coin scanner-equivalent non-event controls per event.
3. One deterministic scanner-equivalent non-event background sample for every canonical Binance Spot symbol.
4. Full-universe daily bars and raw BTCUSDT, ETHUSDT and BNBUSDT reference data.

## Output

- `CHATGPT_25PCT_RESEARCH_INDEX.zip`
- `DISCOVERY_2026_25PCT_UNIVERSE_REFERENCE.zip`
- every numbered `DISCOVERY_2026_25PCT_SYMBOLS_PART_*.zip`

The 25% event population is expected to be materially larger than the prior 50% population, so the exporter may create more numbered ZIP parts and take longer. Packages remain split below the upload target.

## Upgrade

No Supabase migration is required from V10.2.1. Replace the repository files, redeploy both Render services, confirm `/health` reports `11.0.0`, run a new 25% scan, and then run a new export. The previous 50% scan cannot be reused.
