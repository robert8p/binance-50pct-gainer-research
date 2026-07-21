# Data contract — v3.0.0

## Positive event

The event unit remains the earliest qualifying surge for a selected Binance Spot pair on a UTC day.

```text
later-minute high >= eligible earlier-minute low × 1.50
```

The baseline minute must precede the crossing minute and its open time must be no more than 179 minutes earlier. Exact aggregate trades must prove the low-to-crossing interval is no more than 10,800 seconds.

The 60-day primary export includes only events that passed the configured seller-side executed-liquidity test.

## Matched sample unit

Each positive event is a match group containing:

- one positive event anchor;
- up to the configured number of same-symbol control anchors;
- one feature row per sample and decision horizon.

Default decision horizons are 15, 30, 60 and 120 minutes before the anchor.

## Control eligibility

A control:

- uses the same symbol as its positive event;
- falls inside the same chronological split;
- prefers the same UTC minute of day and weekday;
- is not within 24 hours of a known saleable event for that symbol;
- has no detected rolling 50% crossing from the earliest decision horizon through 180 minutes after the control anchor;
- has at least 98% of the configured prior-history minutes;
- has complete local minutes around the decision and outcome windows;
- meets the configured five-minute executed quote-volume floor at every decision horizon.

Returns, volume and volatility are not used to rank control matches.

## Predictor cutoff

For a decision timestamp, the last eligible predictor bar is the one-minute bar opening one minute before the timestamp's minute.

Example:

```text
decision timestamp: 12:19:20 UTC
last predictor bar open: 12:18:00 UTC
```

The 12:19 bar is excluded because it was not complete at 12:19:20.

## Features

Features include multi-horizon price returns and ranges, realised volatility, path drawdowns/run-ups, quote volume, trade counts, taker-buy ratios, acceleration, 24-hour position, same-time historical volume and BTC/ETH/BNB context.

Outcome columns are explicitly prefixed `outcome_` and must not be used as predictors.

## Splits

Whole event dates are assigned chronologically to discovery, validation and sealed-test sets. Calendar days between event dates inherit the surrounding split, and controls remain inside their event's split.

## Dependence

Rows share coins, events and overlapping minute history. Statistical analysis must cluster at least by match group and symbol and must account for testing multiple features and horizons.
