# Binance 50% Exact Entry Validation — V12.0.0

V12 tests the two entry triggers discovered from the opened 2026 50%-within-eight-hours research on a separate, earlier validation period.

## Frozen validation period

- 2025-01-01 inclusive
- 2025-07-01 exclusive
- The reserved 2025-07-01 to 2025-11-01 sealed period is not accessed.

## Strategies

1. **E1 broad momentum confirmation:** entry after abnormal trade participation, abnormal volume expansion, or re-acceleration after a pullback.
2. **E2 R48 armed then confirmation:** first require the fixed R48 recovery/volume state, then wait for the same confirmation.

Signals are evaluated after every completed one-minute bar across the canonical Binance Spot universe.

## Execution

- Position: 500 quote units, normally USDT.
- Entry: first buyer-initiated aggregate trades after the signal, within 60 seconds.
- Primary exit: +15% target or 24-hour time exit.
- Stop-loss: none.
- Exit: seller-initiated aggregate trades within five minutes after the exit trigger.
- Fees: 10 basis points per side.
- Maximum selected entries: five per UTC day per strategy.
- Diagnostics: exact 8h, 24h and 32h MFE/MAE and +10%, +15%, +25% and +50% target touches.

No parameter may be changed after the validation results are opened. Failure retires the strategy. Passing permits a separately built sealed test.

## Output

The completed job creates `ENTRY_VALIDATION_2025_RESULTS.zip`. Download it and upload it to ChatGPT for independent interpretation.

## Important limitation

The symbol universe is based on coins tradeable when the job runs. Historically delisted coins are absent, so survivorship bias is reported explicitly.
