# Binance 3-Hour 50% Surge Research App

A deployable GitHub, Render and Supabase application for studying Binance Spot coins that rose at least **50% within three hours** during the previous **60 completed UTC days**.

The app is historical research infrastructure. It does not place orders, connect to a Binance trading account or claim that past surges predict future surges.

## Version 3.0.0

Version 3 preserves the v2 scanner and positive-event archive, then adds a **matched non-surge control round** so apparent pre-surge patterns can be compared with ordinary periods for the same coin.

For the current 63-event scan, the default five controls per event target approximately **315 matched controls**.

## Stage 1 — 60-day surge census

A candidate is the earliest minute on a UTC day where:

```text
later one-minute high >= lowest eligible prior one-minute low × 1.50
```

The baseline minute must precede the crossing minute. The baseline-minute-open gap is capped at 179 minutes, allowing exact aggregate trades to prove that the low-to-crossing interval did not exceed three hours.

The move may cross midnight. The price only needs to touch +50%; it does not need to close or remain there.

## Saleability definition

A candidate passes the default saleability test when at least **500 quote units** of seller-initiated trades execute at any price during the five minutes after the exact crossing trade.

This is evidence that a small historical exit was possible. It is not reconstructed order-book depth and does not guarantee an exit at the +50% threshold.

## Stage 2 — Positive-event archive

For saleable events, the app can collect:

- ten prior complete UTC days;
- official one-minute and optional one-second kline archives;
- optional aggregate-trade and raw-trade archives;
- event-day data cut off strictly before the crossing minute;
- hashes, source URLs and quality warnings.

This archive is useful for audit and microstructure research, but positive events alone cannot establish a leading indicator.

## Stage 3 — Matched-control analysis

The matched-control job creates same-coin non-surge comparison windows.

Default design:

- five controls per positive event;
- same Binance symbol;
- same chronological data split;
- exact UTC clock-time preference, then small clock-time tolerances;
- no matching on returns, volume or volatility, because doing so could erase the signal being tested;
- exclusion of controls within 24 hours of a known event;
- exclusion of any control near another 50% rolling crossing;
- minimum 500 quote units of executed volume during each five-minute pre-entry check;
- decision horizons of 15, 30, 60 and 120 minutes before the event/control anchor;
- predictors calculated only from fully completed one-minute bars before the decision timestamp.

The app calculates a wide pre-registered feature set covering:

- multi-horizon returns, ranges, run-ups and drawdowns;
- realised volatility;
- quote-volume and trade-count intensity;
- taker-buy imbalance;
- acceleration and relative-volume measures;
- distance from 24-hour highs and lows;
- candle structure;
- same-time historical volume comparisons;
- BTC, ETH and BNB market context;
- data completeness and pre-entry liquidity flags.

## Historical split protection

Whole UTC event dates are assigned chronologically to:

```text
discovery: 70%
validation: 15%
sealed test: 15%
```

Controls stay within the same date range as their matched event.

The job creates four downloads:

- `matched_control_index.zip` — design, quality and package manifest only;
- `matched_control_discovery.zip` — hypothesis generation;
- `matched_control_validation.zip` — one-time validation after candidate rules are fixed;
- `matched_control_sealed_test.zip` — final historical test; do not inspect early.

Rows are clustered by coin, event and overlapping time. Row count must never be treated as independent sample size.

## Infrastructure

- **GitHub:** source control and automated tests.
- **Render web service:** password-protected dashboard.
- **Render worker:** long-running scans and data preparation.
- **Render persistent disk:** verified one-minute archive cache and restart recovery.
- **Supabase Postgres:** jobs, events, matches and audit records.
- **Supabase Storage:** private research packages.

No Binance API key is required. Public market-data endpoints and Binance's official public archive are used.

## Deployment

For an existing v2 installation, follow `WINDOWS_UPDATE.md` or `ANDROID_UPDATE.md` and run:

```text
supabase/migrate_v2_to_v3.sql
```

For a fresh installation, run the complete `supabase/schema.sql`.

After deployment, `/health` should report:

```json
{"status":"ok","version":"3.0.0"}
```

## Main limitations

- The initial universe is based on coins currently reported as Binance Spot-tradeable, so delisted historical coins can be missing.
- Exchange-level tradability does not guarantee availability to a particular UK account or Binance entity.
- One-minute matched controls cannot support event-versus-control claims about one-second or trade-level features. Those require a later symmetric microstructure collection round.
- A matched association is not yet a trading rule. Fees, slippage, entry mechanics, exits, multiplicity and clustered inference still need testing.
