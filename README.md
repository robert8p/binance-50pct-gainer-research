# Binance Momentum Continuation Backtest — V9.0.0

V9 performs the final OHLCV-only research test in this programme.

It does **not** try to predict the beginning of a 50% surge. H1, H2 and H3 are retired. Instead, V9 asks whether the previously frozen late-momentum condition can still produce a repeatable continuation profit when evaluated continuously across Binance Spot history.

## Frozen signal

After every completed one-minute bar, the coin signals when recent five-minute quote volume is at least 500 quote units and at least three of these four conditions pass:

1. 15-minute return is at least 0.9%.
2. 15-minute quote volume is at least 12 times its median at the same UTC time over the preceding seven days, with at least five reference days.
3. Price is at least 74% of the way from its 24-hour low to its 24-hour high.
4. Maximum low-to-later-high run-up during the latest 15 minutes is at least 3.3%.

## Frozen historical test

- Window: 1 July 2025 to 1 November 2025, end exclusive
- Canonical pair preference: USDT, then USDC, then FDUSD
- Current-tradeable Binance Spot universe
- Position: 500 quote units
- Entry: aggregate buyer-initiated executions beginning after the completed signal minute
- Entry fill window: 60 seconds
- Take profit: +10%
- Stop loss: -5%
- Maximum hold: three hours
- Exit: seller-initiated aggregate executions
- Exit fill window: five minutes
- Fees: 0.10% per side
- Same-coin cooldown: three hours after exit or failed execution
- Maximum filled entries: five per UTC day

All parameters and dates are fixed in code and in `docs/V9_PREREGISTERED_PROTOCOL.json`.

## Graduation standard

V9 passes only if every frozen condition passes, including:

- at least 100 completed trades and 20 coins;
- positive net P&L;
- at least 1 quote unit of average net profit per trade;
- profit factor of at least 1.25;
- maximum drawdown no greater than 1,500 quote units on a simulated 10,000-unit starting equity;
- no more than ten consecutive losses;
- no coin contributing more than 15% of trades;
- at least 20 trades and positive expectancy in each chronological third;
- positive lower bound of the 95% coin-cluster bootstrap interval for expectancy;
- at least 95% mean minute-archive coverage;
- signal-generation failure rate no higher than 5% of the universe.

A pass permits a separate implementation and robustness review. It does not initiate live trading. A fail retires this OHLCV-only Binance surge programme without retuning.

## Output package

`continuous_backtest_results.zip` contains:

- `backtest_results.json`
- `backtest_protocol.json`
- `candidate_signals.csv`
- `executed_trades.csv`
- `performance_by_chronological_third.csv`
- `performance_by_month.csv`
- `performance_by_symbol.csv`
- `daily_performance.csv`
- `minute_data_coverage.csv`
- `aggregate_trade_coverage.csv`

## Material limitation

The historical universe begins with coins tradeable on Binance when V9 is run. Historically delisted coins are absent, so survivorship bias remains. The result must be interpreted with that limitation even if every formal criterion passes.
