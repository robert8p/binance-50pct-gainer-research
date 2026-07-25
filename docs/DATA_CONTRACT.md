# Data contract — V10.0.0

## Purpose

V10 exports neutral raw evidence for ChatGPT-led pattern discovery. It does not contain a preferred predictor, model or trade rule.

## Event definition

A saleable event is a later one-minute high at least 50% above the latest occurrence of the lowest prior-minute low in the scanner's conservative 480-minute rolling window, with at least 500 quote units of seller-initiated executions within five minutes after the exact crossing trade.

## Control definition

Each event is paired with up to five same-symbol controls from the same chronological split. At a candidate pseudo-cross minute, the control baseline is selected using the identical scanner algorithm:

- inspect the prior 479 completed minute bars;
- identify the minimum low;
- choose the latest equal occurrence;
- reject if the selected baseline rises 50% within the following 480-minute window;
- reject timestamps or baselines within 24 hours of a known same-symbol event;
- require the same event-duration band;
- require substantially complete ten-day history;
- do not reuse a control baseline in another matched group.

## Sample metadata

`samples.csv` contains one row per labelled event or control, including:

- `sample_id` and `match_group_id`;
- `label` and `sample_type`;
- symbol, base asset and quote asset;
- baseline and crossing/pseudo-cross timestamps;
- ten-day history start and end;
- event and selected-baseline duration bands;
- matching diagnostics;
- explicitly prefixed `outcome_` fields.

## Raw minute data

`minute_data/*.parquet` stores each physical symbol/time row once. Fields are:

- open time;
- OHLC;
- base and quote volume;
- trade count;
- taker-buy base and quote volume;
- observed-data flag.

Use `analysis_loader.py` or the bounds in `samples.csv` to reconstruct each sample's ten-day window. Missing bars are retained as missing and are never forward-filled.

## Reference market data

`reference_data/*.parquet` contains raw BTCUSDT, ETHUSDT and BNBUSDT one-minute series for the relevant split period. The app does not combine or weight these references.

## Partitions

Whole UTC event dates are assigned chronologically:

- discovery: 60%;
- validation: 20%;
- sealed test: 20%.

Only discovery should be opened initially. Candidate features, rules and acceptance criteria must be frozen before validation is opened. The sealed test remains closed until one final rule survives validation without retuning.
