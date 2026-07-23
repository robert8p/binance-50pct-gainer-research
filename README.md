# Binance 3-Hour 50% Surge Research App

Historical research infrastructure for Binance Spot coins that rose at least **50% within three hours** and were demonstrably saleable after the crossing.

The app does not connect to a Binance trading account or place orders.

## Version 6.0.0

V6 adds the two tests required after the baseline-aligned exploratory analysis:

1. **Automatic fresh historical confirmation** of the frozen H1 precursor.
2. **A continuous, executable-entry historical backtest** that is unlocked only when confirmation passes.

The preferred evidence sequence is fixed before results are opened:

- Fresh confirmation: **1 January–1 March 2026**.
- Sealed continuous backtest: **1 March–22 May 2026**.

These periods do not overlap the already opened May–July dataset.

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

The app automatically opens all staged packages only after the rule and acceptance criteria have been frozen in code. No dashboard field can retune the thresholds.

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

1. H1 becomes true on a rising edge and arms the coin for three hours.
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

## Upgrade from V5

Run:

```text
supabase/migrate_v5_to_v6.sql
```

Then replace the GitHub repository files with V6 and wait for both Render services to redeploy.

The health route should show:

```json
{"status":"ok","version":"6.0.0"}
```

Follow `WINDOWS_UPDATE.md` for the simplest route.

## Material limitations

- The historical universe begins with coins tradeable on Binance when the job runs. Delisted historical coins are absent, creating survivorship bias.
- Aggregate executed trades are a defensible fill proxy, not a reconstruction of historical order-book depth.
- Current Binance availability does not guarantee availability to a particular UK account or entity.
- Backtest results do not guarantee future performance.
- One fixed exit specification is tested. It must not be changed after seeing the result and then described as sealed evidence.
