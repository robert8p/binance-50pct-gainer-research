# Changelog

## 2.0.0

- Replaced previous-day-close events with rolling three-hour +50% events.
- Reduced and capped the dashboard horizon at 60 completed UTC days.
- Added exact baseline-low trade resolution and exact three-hour proof.
- Allowed cross-midnight events and first listing days.
- Removed any requirement for the price to remain at +50%.
- Changed saleability to seller-initiated executed turnover at any price after crossing.
- Added exit VWAP and price-quality metrics.
- Made the main event CSV saleability-only and added an all-candidates audit CSV.
- Added an additive v1-to-v2 Supabase migration and Android upgrade guide.
