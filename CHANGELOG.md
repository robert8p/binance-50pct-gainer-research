# Changelog

## 7.0.0

- Broadened the qualifying rise window from three hours to eight hours.
- Updated controls, contamination audits, baseline alignment and outcome diagnostics to the 480-minute event definition.
- Retained the separate three-hour maximum trade hold; only the target-event and precursor-to-continuation windows changed.
- Prior three-hour scans and research packages remain historical reference and are excluded from V7 workflow dropdowns.
- Added Supabase migration `migrate_v6_to_v7.sql`.

## 6.0.0

- Added automatic H1 fresh historical confirmation.
- Added frozen acceptance criteria and matched-set permutation testing.
- Added a hard gate preventing the trading backtest after failed confirmation.
- Added continuous minute-by-minute H1 and late-trigger evaluation.
- Added exact post-signal entry timing.
- Added historical aggregate-trade entry and exit fill reconstruction.
- Added fixed +15% take profit, −5% stop, three-hour time exit and two-sided fees.
- Added maximum five filled entries per UTC day and symbol cooldown.
- Added expectancy, profit factor, drawdown, consecutive-loss and concentration outputs.
- Added source coverage, fill-failure and survivorship-bias reporting.
- Added Supabase migration `migrate_v5_to_v6.sql`.

## 5.0.0

- Added baseline-aligned ten-day context and pseudo-baseline control audits.
