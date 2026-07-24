# Data contract — V8.0.0

## Event definition

A saleable event is a later one-minute high at least 50% above the latest occurrence of the lowest prior-minute low in the scanner's conservative 480-minute rolling window, with at least 500 quote units of seller-initiated executions within five minutes after the exact crossing trade.

## V8 confirmation population

Each event is paired with up to five same-symbol controls. At a matched pseudo-cross time, the control baseline is selected using the identical scanner algorithm:

- inspect the prior 479 completed minute bars;
- identify the minimum low;
- choose the latest equal occurrence;
- reject if the selected baseline rises 50% within the next 479 later minute bars;
- require the same event-duration band;
- require complete ten-day history and five-minute liquidity of at least 500 quote units.

## Frozen H3 signal

```text
volatility_1d_to_7d_ratio >= 0.4
AND ret_prior_1d_to_7d_pct <= 5
```

## Confirmation outputs

`fresh_confirmation_results.zip` contains:

- `fresh_confirmation_results.csv`
- `duration_band_results.csv`
- `fresh_confirmation_population.csv`
- `algorithmic_local_low_controls.csv`
- `control_rejections.csv`
- `source_manifest.csv`
- `split_summary.csv`
- `confirmation_decision.json`
- `V8_PREREGISTERED_PROTOCOL.json`

## Backtest protocol

Protocol: `v8_h3_continuous_executable_backtest_1`.

H3 arms a symbol for 480 minutes. The unchanged late trigger must occur within the arm window. The trade uses a 500-quote-unit entry, +15% take profit, −5% stop loss, three-hour maximum hold, 0.10% fee per side, three-hour symbol cooldown and five filled entries per UTC day.
