# V11 data contract

## Labels

- `label=1`, `sample_type=event`: saleable >=25% rise from the selected local-low baseline within eight hours.
- `label=0`, `sample_type=same_coin_control`: same-coin scanner-equivalent local-low window that does not rise 25% within eight hours.
- `label=0`, `sample_type=universe_background`: deterministic scanner-equivalent local-low window from the full canonical Binance universe that does not rise 25% within eight hours.

## Raw history

Each sample points to ten days of deduplicated one-minute OHLCV, quote volume, trade count and taker-buy fields. The app creates no predictive features and selects no rule.

## Research status

All 2026 25% evidence is exploratory discovery. Earlier 50% findings are not validation evidence for this target.
