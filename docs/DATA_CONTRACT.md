# Data contract — v7.0.0

## Target event

A V7 event is the earliest later-minute high at least 50% above a prior-minute low within a conservative 480-minute rolling window. Same-minute low-to-high movement is excluded.

An event is saleable only when at least 500 quote units of seller-initiated executed notional are observed within 300 seconds after the exact threshold-crossing trade.

Key identifiers include:

```text
event_definition_version = v7_rolling_8h
window_minutes = 480
```

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

V7 baseline offsets include:

```text
14400,10080,7200,4320,2880,1440,720,480,360,180,60,0
```

Window suffixes are minute counts. Examples:

```text
ret_14400m_pct = ten-day return ending at the snapshot
ret_prior_1d_to_7d_pct = return from seven days before to one day before the snapshot
volume_last1d_vs_prior2d_daily_rate = latest day volume / prior two-day daily rate
```

Columns beginning `outcome_` are diagnostics or labels and are prohibited predictors. V7 forward diagnostics use the next eight hours where applicable.

## Continuation row

`continuation_trigger_features.csv` contains one row per sample at the frozen 15-minute horizon before the crossing/control anchor. It includes the four component flags and `frozen_late_trigger_pass`.

In the continuous backtest, H1 arms a symbol for 480 minutes. The unchanged continuation trigger must occur during that arm window.

## Control audit

`control_contamination_audit.csv` records:

```text
pseudo_window_observed_fraction
pseudo_window_crossing_detected
pseudo_window_max_sequential_gain_pct
pseudo_window_contaminated_control
```

V7 controls are protected across the eight-hour pseudo-event window and must include the mandatory 480-minute decision horizon. Flagged controls are not clean negative observations.

## Packages

Exploratory reuse:

- `baseline_context_index.zip`
- `baseline_context_exploratory.zip`

Fresh staged:

- `baseline_context_index.zip`
- `baseline_context_discovery.zip`
- `baseline_context_validation.zip`
- `baseline_context_sealed_test.zip`

## V7 confirmation result

`fresh_confirmation_results.zip` contains:

- `fresh_confirmation_results.csv`: split and overall H1 rates;
- `fresh_confirmation_population.csv`: exact quality-pass offset-0 population used;
- `source_manifest.csv`: source package hashes;
- `confirmation_decision.json`: frozen checks and pass/fail decision.

The confirmation protocol identifier is:

```text
v7_h1_8h_fresh_confirmation_1
```

## V7 continuous backtest result

`continuous_backtest_results.zip` contains:

- `candidate_signals.csv`: all eligible two-stage signal timestamps before portfolio suppression;
- `executed_trades.csv`: suppression, fill and completed-trade records;
- `minute_data_coverage.csv`;
- `aggregate_trade_coverage.csv`;
- `backtest_protocol.json`;
- `backtest_results.json`.

The backtest protocol identifier is:

```text
v7_continuous_executable_backtest_1
```

A `completed` execution row records exact entry and exit VWAPs, fill timestamps, fees, gross return, net return and quote-currency P&L. Rows with `entry_not_filled`, `exit_not_filled`, cooldown or daily-cap statuses remain in the audit trail and are not silently discarded.

The target-event and arm windows are eight hours. The frozen execution maximum hold remains three hours.
