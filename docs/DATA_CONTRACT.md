# Data contract — V10.2.1

## Labels

- `label=1`, `sample_type=event`: saleable >=50% rise within eight hours.
- `label=0`, `sample_type=same_coin_control`: same-symbol negative selected using the same rolling-local-low algorithm.
- `label=0`, `sample_type=universe_background`: deterministic negative from any canonical symbol, including symbols with no qualifying event.

## Raw minute files

Each symbol part contains deduplicated one-minute Binance kline fields. `samples.csv` provides each sample's exact history bounds. No predictive features or imputations are supplied.

## Universe reference

`DISCOVERY_2026_UNIVERSE_REFERENCE.zip` contains:

- `universe_symbols.csv`
- `universe_daily_data.parquet`
- raw BTCUSDT, ETHUSDT and BNBUSDT minute bars

## Research status

All 2026 evidence is exploratory. Separate historical periods are required for validation and sealed testing after ChatGPT freezes candidate rules.
