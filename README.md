# Binance ChatGPT Research Exporter — V10.2.1

V10.2 keeps the application neutral: it collects, labels, audits and packages Binance evidence; ChatGPT performs feature generation and pattern discovery.

## Research window

- Start: 2026-01-01 inclusive
- End: 2026-07-25 exclusive
- Outcome: saleable >=50% low-to-later-high rise within eight hours
- Treatment: all 2026 data are exploratory discovery evidence

## Full-universe correction

V10.1 exported only coins that had at least one qualifying event. V10.2 covers every canonical Binance Spot symbol in the source scan.

It exports:

1. Every saleable event with ten days of raw one-minute history.
2. Up to five same-coin scanner-equivalent controls per event.
3. One deterministic scanner-equivalent non-event background window for every canonical symbol, including coins with no qualifying event.
4. Full-universe daily OHLCV/trade data.
5. Raw BTCUSDT, ETHUSDT and BNBUSDT one-minute reference data.
6. A symbol inventory showing event counts, background coverage and failures.

The app does not calculate predictive features, optimise thresholds or define a trading rule.

## Output

Large evidence is divided by symbol into upload-sized files:

- `CHATGPT_RESEARCH_INDEX.zip`
- `DISCOVERY_2026_UNIVERSE_REFERENCE.zip`
- `DISCOVERY_2026_SYMBOLS_PART_001.zip`
- further numbered symbol parts as required

Upload the index, reference package and every numbered symbol part to ChatGPT.

## Cancellation

Queued or running neutral exports can be cancelled from the dashboard. Cancellation is cooperative: the worker stops after the current symbol operation and cleans its temporary job directory.

## Upgrade

No new Supabase migration is required when V10.0 or V10.1 is already installed. Replace the repository files, redeploy both Render services, confirm `/health` reports `10.2.1`, and queue a new export from the completed 2026 scan.
