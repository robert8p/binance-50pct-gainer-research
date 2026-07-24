# V8 quality report

## Integrity controls

- H3 thresholds are fixed in code and in `docs/V8_PREREGISTERED_PROTOCOL.json`.
- Event and control baselines use the same rolling-minimum selection algorithm.
- Equal minimum lows resolve to the latest occurrence, matching the scanner deque.
- Controls are rejected if the selected low rises 50% within the following eight-hour window.
- Controls are matched within the same symbol and chronological split and must share the event-duration band.
- Ten complete days of pre-baseline history and 500 quote units of five-minute liquidity are required.
- Matched randomisation and symbol-cluster bootstrap inference are included.
- Validation and sealed chronological direction are explicit acceptance conditions.
- The continuous backtest remains inaccessible after a failed confirmation.

## Local validation

- Python compilation passed.
- 49 network-free tests passed.
- Jinja dashboard parsing and route smoke checks passed during packaging.
- Clean-extraction hash and repeat-test checks are performed before release.

Two unchanged positive-event archive tests require PyArrow. PyArrow was unavailable in the offline local build environment, so those two tests could not be collected locally. PyArrow remains pinned in `requirements.txt`, and the complete suite runs in GitHub Actions and Render.

## Remaining limitations

- Historical universe membership still begins from the currently tradeable Binance universe, creating survivorship bias for delisted coins.
- Algorithmically matched controls are materially fairer than arbitrary timestamps, but only a continuous all-minute test can establish real alert frequency and precision.
- A three-hour maximum trade hold is retained separately from the eight-hour target-event definition.
