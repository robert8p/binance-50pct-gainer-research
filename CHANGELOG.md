# Changelog

## 8.0.0

- Replaced fresh H1 confirmation with the frozen H3 volatility-reversal hypothesis.
- Added scanner-equivalent algorithmic local-low controls.
- Rejected controls that subsequently rise 50% within the following eight-hour window.
- Matched controls by symbol, chronological split, pseudo-cross clock time and event-duration band.
- Added matched randomisation inference, symbol-cluster bootstrap intervals and duration-band reporting.
- Updated the continuous backtest to arm on H3 rather than H1.
- Preserved the unchanged late-momentum continuation trigger and fixed execution assumptions.
- Added V7-to-V8 Supabase migration and confirmation issue logging.

## 7.0.0

- Broadened the qualifying rise window from three hours to eight hours.
