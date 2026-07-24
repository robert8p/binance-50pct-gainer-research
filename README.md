# Binance 8-hour 50% surge research — V8.0.0

V8 corrects the main control-design weakness identified in the exploratory eight-hour analysis.

## Research objective

Find a repeatable, historically robust way to identify saleable Binance Spot coins before or during the early stages of a rise of at least 50% within eight hours.

A qualifying event must also prove at least 500 quote units of seller-initiated executed notional within five minutes after the exact crossing trade.

## What V8 changes

The event scanner itself is unchanged: it uses the latest occurrence of the lowest one-minute low in the prior 479 completed minutes and identifies a later high at least 50% above that low.

V8 fresh confirmation now selects non-event controls using the **same algorithm**:

1. Choose a matched pseudo-cross minute for the same coin and chronological split.
2. Select the latest occurrence of the minimum low in the preceding 479 completed minutes.
3. Require the selected baseline to fall in the same event-duration band.
4. Reject the control if that low rises 50% or more during the following eight-hour window.
5. Require ten complete days of history and at least 500 quote units of five-minute pre-baseline liquidity.

This removes the earlier asymmetry where event baselines were retrospectively selected lows but control baselines were ordinary timestamps.

## Frozen precursor

V8 tests only the unchanged H3 volatility-reversal rule:

- `volatility_1d_to_7d_ratio >= 0.4`
- `ret_prior_1d_to_7d_pct <= 5`

No threshold can be edited from the dashboard.

## Fresh confirmation period

Use an explicit eight-hour historical scan covering:

- Start inclusive: `2025-11-01`
- End exclusive: `2026-01-01`

This period predates the opened May–July eight-hour exploratory sample.

## Preregistered acceptance

H3 passes only if all checks succeed:

- at least 25 evaluable events;
- event signal rate at least 30%;
- control signal rate no higher than 30%;
- event/control rate ratio at least 1.5;
- matched randomisation p-value no higher than 0.05;
- at least eight distinct event symbols hit;
- symbol-cluster bootstrap rate-ratio lower bound above 1;
- positive direction in both validation and sealed chronological segments;
- positive direction in at least two duration bands containing at least five events.

A failed result keeps the continuous backtest locked.

## Continuous backtest after a pass

The frozen sequence is:

1. H3 becomes true on a rising edge and arms the coin for eight hours.
2. The unchanged late-momentum trigger must occur during that arm window.
3. Enter using buyer-initiated aggregate trades after the completed trigger minute.
4. Prove a 500-quote-unit fill.
5. Exit at +15%, −5%, or after three hours, using seller-initiated aggregate trades.
6. Apply 0.10% fees on each side, a three-hour symbol cooldown and a maximum of five filled entries per UTC day.

The eight-hour target window and three-hour maximum trade hold are deliberately separate.

## Deployment

Existing installations should run:

```text
supabase/migrate_v7_to_v8.sql
```

Then upload the V8 files to the existing GitHub repository and wait for both Render services to redeploy.

Health check:

```json
{"status":"ok","version":"8.0.0"}
```

See `WINDOWS_UPDATE.md` for the simplest upgrade and run sequence.
