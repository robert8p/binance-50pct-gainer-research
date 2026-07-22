# Binance 3-Hour 50% Surge Research App

A deployable GitHub, Render and Supabase application for studying Binance Spot coins that rose at least **50% within three hours** and were demonstrably saleable after crossing.

The app is historical research infrastructure. It does not place orders, connect to a Binance trading account or claim that historical associations are profitable.

## Version 4.0.0

Version 4 retains the 60-day/custom-date surge scanner, positive-event archive and matched controls, then adds a **full ten-day context engine**.

For every event and matched control, it calculates predictors using only completed one-minute bars before decision times 15, 30, 60 and 120 minutes before the anchor.

## What the ten-day round measures

Feature windows:

```text
15m, 30m, 1h, 2h, 3h, 6h, 12h,
1d, 2d, 3d, 5d, 7d and 10d
```

Feature families include:

- returns, range position, distance from highs/lows, trend slope and trend consistency;
- run-up, drawdown, recovery and return acceleration;
- quote volume, trade count, average trade size and taker-buy ratio;
- volatility and range compression/expansion;
- daily price, volume and range trends;
- one-minute shock counts, hourly volume spikes, breakout attempts and failed breakouts;
- activity relative to the same UTC time during the prior seven days;
- relative strength versus BTC, ETH, BNB and an equal-weight market proxy;
- ten-day completeness and minimum entry liquidity.

Columns beginning `outcome_` are diagnostics/labels and must never be used as predictors.

## Existing data versus fresh evidence

The previously opened 63-event dataset can be processed in **exploratory reuse** mode. It is useful for discovering ten-day feature families, but it cannot prove a new rule because its validation and sealed splits have already been inspected.

For fresh evidence, v4 also supports fixed historical scan dates. The correct staged workflow is:

1. Queue an earlier historical surge scan using explicit start/end dates.
2. Build same-coin matched controls.
3. Queue ten-day context using **fresh staged** mode.
4. Analyse discovery only.
5. Fix candidate rules before opening validation.
6. Open validation once without retuning.
7. Keep sealed test unopened until the final rule is frozen.

## Existing core definitions

A surge is the earliest later-minute high at least 50% above an eligible prior-minute low within the conservative three-hour rolling window. The price only needs to touch the threshold.

A candidate is saleable when at least 500 quote units of seller-initiated aggregate trades execute at any price during the five minutes following the exact crossing trade.

## Infrastructure

- GitHub: source control and automated tests.
- Render web service: password-protected dashboard.
- Render worker: scans and research jobs.
- Render persistent disk: verified archive cache and restart recovery.
- Supabase Postgres: jobs, events, controls and audit records.
- Supabase Storage: private downloadable research packages.

No Binance trading credentials are required. Public market-data endpoints and Binance's public archive are used.

## Upgrade

Existing v3 users must run:

```text
supabase/migrate_v3_to_v4.sql
```

before deploying the v4 source files.

After deployment, `/health` should return:

```json
{"status":"ok","version":"4.0.0"}
```

Follow `WINDOWS_UPDATE.md` for the simplest Windows upgrade.

## Main limitations

- Historical scans still begin with the current Binance Spot universe, so delisted coins can be absent.
- Current Binance exchange tradability does not guarantee availability to a specific UK account or entity.
- Ten-day matched associations are not executable strategies until continuously tested with fixed entry, exit, fees, slippage and cooldown rules.
- Samples are clustered by symbol and event; row counts overstate independent evidence.
