# Binance 3-Hour 50% Surge Research App

A deployable GitHub, Render and Supabase application for studying Binance Spot coins that rose at least **50% within three hours** and were demonstrably saleable after crossing.

The app is historical research infrastructure. It does not place orders, connect to a Binance trading account or claim that historical associations are profitable.

## Version 5.0.0

Version 5 corrects the principal alignment flaw found in the ten-day analysis.

Earlier context rows were measured backwards from the later +50% crossing. In most events, that meant the “15–120 minutes before” observations were already inside the surge. V5 adds a new **baseline-aligned context engine** that measures only information available before the minute containing the low from which the qualifying three-hour move began.

The crossing-aligned v4 output remains available for audit continuity, but the new Step 5 output is the correct source for precursor research.

## Two-stage design

### 1. Precursor stage

For every event and same-coin control, V5 creates snapshots:

```text
10d, 7d, 5d, 3d, 48h, 24h, 12h, 6h, 3h, 1h and 0m
before the baseline minute
```

At every snapshot it calculates the existing multi-timescale windows up to ten days. The offset-0 row ends at the final completed minute before the detected surge baseline.

### 2. Continuation stage

The prior 15-minute momentum rule is preserved unchanged and evaluated separately 15 minutes before the +50% crossing. It is not presented as a predictor of surge initiation.

## Symmetric control alignment

Events use the scanner’s baseline minute. Each control receives a pseudo-baseline equal to:

```text
control anchor − matched event's baseline-to-cross duration in whole minutes
```

Both event and control baselines are therefore minute-level. Exact event aggregate-trade prices remain metadata/outcomes rather than asymmetric predictors.

Every control is re-audited for an accidental 50% sequential low-to-later-high move inside its pseudo-event window. Contaminated controls are explicitly flagged and excluded from clean analysis.

## Frozen hypotheses for the fresh round

The app writes three preregistered precursor hypotheses into every package:

1. Weak/flat prior week followed by one-day price and volume ignition.
2. Coin-specific one-day acceleration relative to BTC, ETH and BNB.
3. Volatility activation after a weak/flat prior week.

Thresholds and the 15-minute continuation trigger are fixed in code and package metadata. They cannot be changed through the dashboard.

## Existing data versus fresh evidence

The May–July 2026 dataset must be run as **exploratory reuse** because all prior splits have been opened.

Fresh staged mode requires:

- an explicit earlier historical scan ending on or before **22 May 2026**;
- matched controls built with the `180`-minute horizon included, so the full pseudo-event interval has contamination protection;
- discovery, validation and sealed packages opened in sequence.

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

No Binance trading credentials are required.

## Upgrade

Existing v4 users must run:

```text
supabase/migrate_v4_to_v5.sql
```

before deploying the v5 source files.

After deployment, `/health` should return:

```json
{"status":"ok","version":"5.0.0"}
```

Follow `WINDOWS_UPDATE.md` for the simplest Windows upgrade.

## Main limitations

- Historical scans begin with the current Binance Spot universe, so delisted coins can be absent.
- The event baseline is known retrospectively. Baseline alignment corrects causal ordering but does not itself tell a live scanner when to alert; any surviving rule must later be evaluated every minute.
- A pseudo-baseline is a matched timing construct, not a claim that a control had a true latent surge start.
- The offset-10-day snapshot needs another ten days of preceding feature history, so V5 may download roughly 20 days before the earliest baseline.
- Associations remain non-tradeable until they survive fresh staged evidence and a continuous executable-entry backtest.
- Samples are clustered by symbol and event; row counts overstate independent evidence.
