# Data contract — v4.0.0

## Ten-day context row

Each row is one event/control sample at one decision horizon.

Identity columns include `sample_id`, `match_group_id`, `sample_type`, `label`, `split`, `symbol`, `anchor_time`, `decision_time` and `decision_horizon_minutes`.

Predictor columns use completed bars strictly before `decision_time`. Window suffixes are minute counts; for example:

```text
ret_14400m_pct = ten-day return
quote_volume_10080m = seven-day quote volume
position_in_7200m_range = position within the five-day high-low range
```

Columns beginning `outcome_` describe the later path and are prohibited predictors.

Quality columns include `observed_fraction_prior_window`, `missing_minutes_prior_window`, `entry_quote_volume_5m`, `entry_liquidity_pass` and `feature_quality_status`.

## Packages

Exploratory reuse:

- `ten_day_context_index.zip`
- `ten_day_context_exploratory.zip`

Fresh staged:

- `ten_day_context_index.zip`
- `ten_day_context_discovery.zip`
- `ten_day_context_validation.zip`
- `ten_day_context_sealed_test.zip`
