# Data contract — v2.0.0

## Unit of analysis

The event unit is the earliest qualifying surge for a selected Binance Spot pair on a UTC calendar day. One canonical pair is selected per base coin using the quote preference stored in the scan job.

## Scan horizon

The production dashboard defaults to and caps the lookback at **60 completed UTC days**. The current incomplete UTC day is excluded.

## Rolling three-hour event

Minute bars are retrieved from three hours before the event day through the end of the event day. For each later minute, the scanner considers prior minute lows whose minute-open timestamps are no more than 179 minutes earlier.

A candidate occurs when:

```text
crossing-minute high >= baseline-minute low × (1 + threshold_pct / 100)
```

The baseline minute must be earlier than the crossing minute. Same-minute low-to-high moves are excluded.

The 179-minute open-time cap is conservative: even if the baseline low occurs at the beginning of its minute and the crossing occurs at the end of the later minute, exact elapsed time remains below 180 minutes.

The move may cross a UTC-day boundary. First listing days are included even when no previous daily bar exists. In that case `previous_day_bar_available = false` and `previous_day_close` is populated with the first daily-bar open for backward-compatible context only.

## Exact trade proof

The scanner resolves:

- `baseline_trade_time`: latest aggregate trade at the baseline minute’s low;
- `first_cross_trade_time`: first aggregate trade at or above the threshold inside the crossing minute.

A later recross is never substituted for an unresolved crossing because the price is not required to remain above the threshold.

Qualification requires:

```text
0 < first_cross_trade_time - baseline_trade_time <= 10,800 seconds
```

Unresolved baseline or crossing trades remain in the audit candidate set but cannot pass saleability.

## Saleability

Default saleability requires at least 500 quote units of seller-initiated executed turnover at **any price** from the exact crossing through the following 300 seconds.

`buyer_was_maker = true` is interpreted as seller-initiated execution.

The main metric is:

```text
seller_taker_notional_any_price
```

Additional fields measure persistence and exit quality without making them pass conditions:

- `seller_taker_notional_at_or_above`;
- `minimum_exit_vwap`;
- `minimum_exit_vwap_pct_vs_threshold`;
- `minimum_exit_reached_price`;
- `lowest_seller_exit_price`;
- `highest_seller_exit_price`.

The primary event export filters `sellability_pass = true`. The candidate export includes all detected surges.

## Time and cutoff conventions

- Database and API timestamps: UTC.
- Event date: UTC crossing date.
- London observations: 14:00, 17:00 and 19:00 Europe/London with daylight-saving conversion.
- Research predictor cutoff: timestamp strictly before the crossing minute open.
- The complete crossing minute is excluded from predictor data.

## Stored minute data

Event minute storage includes the three-hour lead-in before the UTC day as well as the event day, allowing cross-midnight baselines to be audited.

## Recovery and idempotency

- One event per `scan_id, symbol, event_date`.
- Primary keys prevent duplicate bars and aggregate trades.
- Interrupted worker jobs are requeued.
- Completed research files are reused within the same job.
