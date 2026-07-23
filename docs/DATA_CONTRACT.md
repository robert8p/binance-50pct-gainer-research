# Data contract — v5.0.0

## Baseline-context feature row

Each row is one event/control sample at one fixed offset before its baseline minute.

Identity fields include:

```text
sample_id, match_group_id, sample_type, label, split, symbol,
baseline_anchor_time, cross_anchor_time, baseline_to_cross_minutes,
baseline_snapshot_offset_minutes, decision_time
```

Predictors use completed one-minute bars strictly before `decision_time`.

The primary preregistered precursor test uses offset `0`, whose final predictor bar is the minute immediately before the baseline.

Window suffixes are minute counts. Examples:

```text
ret_14400m_pct = ten-day return ending at the snapshot
ret_prior_1d_to_7d_pct = return from seven days before to one day before the snapshot
volume_last1d_vs_prior2d_daily_rate = latest day volume / prior two-day daily rate
```

Columns beginning `outcome_` are diagnostics/labels and are prohibited predictors.

## Continuation row

`continuation_trigger_features.csv` contains one row per sample at the frozen 15-minute horizon before the crossing/control anchor. It includes the four component flags and `frozen_late_trigger_pass`.

## Control audit

`control_contamination_audit.csv` records:

```text
pseudo_window_observed_fraction
pseudo_window_crossing_detected
pseudo_window_max_sequential_gain_pct
pseudo_window_contaminated_control
```

Flagged controls are not clean negative observations.

## Packages

Exploratory reuse:

- `baseline_context_index.zip`
- `baseline_context_exploratory.zip`

Fresh staged:

- `baseline_context_index.zip`
- `baseline_context_discovery.zip`
- `baseline_context_validation.zip`
- `baseline_context_sealed_test.zip`

## V6 confirmation result

`fresh_confirmation_results.zip` contains:

- `fresh_confirmation_results.csv`: split and overall H1 rates;
- `fresh_confirmation_population.csv`: the exact quality-pass offset-0 population used;
- `source_manifest.csv`: source package hashes;
- `confirmation_decision.json`: frozen checks and pass/fail decision.

## V6 continuous backtest result

`continuous_backtest_results.zip` contains:

- `candidate_signals.csv`: all eligible two-stage signal timestamps before portfolio suppression;
- `executed_trades.csv`: suppression, fill and completed-trade records;
- `minute_data_coverage.csv`;
- `aggregate_trade_coverage.csv`;
- `backtest_protocol.json`;
- `backtest_results.json`.

A `completed` execution row records exact entry and exit VWAPs, fill timestamps, fees, gross return, net return and quote-currency P&L. Rows with `entry_not_filled`, `exit_not_filled`, cooldown or daily-cap statuses remain in the audit trail and are not silently discarded.
