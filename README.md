# Binance 8-Hour 50% Surge Research App

Historical research infrastructure for Binance Spot coins that rose at least **50% within eight hours** and were demonstrably saleable after the crossing.

The app does not connect to a Binance trading account or place orders.

## Version 7.0.0

V7 changes the target event from a 50% rise within three hours to a 50% rise within **eight hours**.

That change applies throughout the research chain:

- discovery scanning;
- exact crossing verification;
- saleability testing;
- matched-control contamination checks;
- baseline alignment;
- ten-day context features;
- fresh historical confirmation;
- the precursor-to-continuation arm window.

Prior three-hour scans and research packages remain in Supabase as historical records, but V7 deliberately excludes them from its workflow selectors. An eight-hour event definition requires a fresh scan and fresh downstream research.

## What remains unchanged

- Latest-scan horizon: **60 completed UTC days** by default.
- Threshold: **50%**.
- Saleability: at least **500 quote units** of seller-initiated executed notional within five minutes after the exact crossing.
- H1 precursor thresholds.
- Late-momentum trigger thresholds.
- Executable trade specification, including the separate **three-hour maximum hold**.

The target event may unfold over eight hours; that does not automatically make an eight-hour hold optimal. The previously frozen three-hour trade hold remains separate so the research question changes only where intended.

## Fresh V7 evidence sequence

Because the January–February 2026 period was already opened under the three-hour definition, the recommended untouched V7 confirmation period is:

- Fresh confirmation: **1 November 2025–1 January 2026**, end exclusive.
- Sealed continuous backtest, only after confirmation passes: **1 March–22 May 2026**, end exclusive.

These windows are fixed in `docs/V7_PREREGISTERED_PROTOCOL.json` before V7 results are opened.

## Frozen precursor: H1 weak-base ignition

At every candidate baseline, H1 requires:

- return during the earlier one-to-seven-day period no higher than **+5%**;
- latest 24-hour return at least **+5%**;
- latest one-day quote volume at least **1.5×** the daily rate of the preceding two days.

Fresh confirmation uses only:

- offset-0 baseline rows;
- quality-pass data;
- at least 500 quote units of prior five-minute liquidity;
- uncontaminated same-coin controls.

The app opens all staged packages only after the rule and acceptance criteria are frozen in code. No dashboard field can retune the thresholds.

## Frozen confirmation criteria

H1 must achieve all of the following:

- at least 15 evaluable surge events;
- event signal rate at least 25%;
- control signal rate no more than 15%;
- event/control rate ratio at least 2.0;
- matched permutation p-value no more than 0.05;
- at least five event symbols detected;
- event rate above control rate in the sealed split.

A failed confirmation does not unlock the continuous backtest.

## Continuous two-stage backtest

After every completed one-minute bar:

1. H1 becomes true on a rising edge and arms the coin for eight hours.
2. The unchanged late-momentum trigger must occur during that arm window.
3. Entry begins only after the completed trigger minute.
4. Historical buyer-initiated aggregate trades must prove a 500-quote-unit entry within 60 seconds.
5. Exit uses historical seller-initiated aggregate trades.

The fixed trade specification is:

- position: 500 quote units;
- take profit: +15%;
- stop loss: −5%;
- maximum hold: three hours;
- exit-fill window: five minutes;
- fees: 0.10% on entry and exit;
- maximum five filled entries per UTC day;
- 180-minute symbol cooldown after exit or failed execution.

The output includes signal frequency, completed trades, fill failures, expectancy, profit factor, drawdown, consecutive losses, symbol concentration, fees and slippage.

## Official data

The application uses Binance public Spot market-data endpoints and Binance's official daily archive for one-minute klines and aggregate trades. Archive checksums are verified when Binance publishes them.

No Binance API key is required.

## Upgrade from V6

Run:

```text
supabase/migrate_v6_to_v7.sql
```

Then replace the GitHub repository files with the extracted V7 package and wait for both Render services to redeploy.

The health route should show:

```json
{"status":"ok","version":"7.0.0"}
```

Follow `WINDOWS_UPDATE.md` for the simplest deployment route.

## Material limitations

- The historical universe begins with coins tradeable on Binance when the job runs. Delisted historical coins are absent, creating survivorship bias.
- Aggregate executed trades are a defensible fill proxy, not a reconstruction of historical order-book depth.
- Current Binance availability does not guarantee availability to a particular UK account or entity.
- Backtest results do not guarantee future performance.
- One fixed exit specification is tested. It must not be changed after seeing the result and then described as sealed evidence.
