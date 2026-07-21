# Changelog

## 3.0.0

- Added same-symbol matched non-surge controls.
- Added five-controls-per-event default and 1–10 configurable range.
- Added 15, 30, 60 and 120-minute decision horizons.
- Added strict pre-decision feature cutoffs using completed one-minute bars only.
- Added broad price, volume, volatility, order-flow-proxy and market-context features.
- Added chronological discovery, validation and sealed historical test packages.
- Added control contamination exclusions around known events and all detected 50% crossings.
- Added pre-entry liquidity and data-completeness checks.
- Added persistent verified one-minute archive caching with public REST fallback.
- Added matched-control job, match, file and issue tables.
- Added an additive v2-to-v3 Supabase migration.
- Added Windows and Android upgrade guides.

## 2.0.0

- Replaced previous-day-close events with rolling three-hour +50% events.
- Reduced and capped the dashboard horizon at 60 completed UTC days.
- Added exact baseline-low trade resolution and exact three-hour proof.
- Allowed cross-midnight events and first listing days.
- Removed any requirement for the price to remain at +50%.
- Changed saleability to seller-initiated executed turnover at any price after crossing.
- Added exit VWAP and price-quality metrics.
- Made the main event CSV saleability-only and added an all-candidates audit CSV.
