# Binance 3-Hour 50% Surge Research App

A deployable GitHub, Render and Supabase application that finds **currently tradeable Binance Spot coins** whose selected pair rose by at least **50% within three hours** during the previous **60 completed UTC days**, and then verifies that the coin had meaningful executed seller-side liquidity after the threshold was reached.

The app is a historical research collector. It does not place orders, connect to a Binance account or claim that a past surge predicts another surge.

## Version 2.0.0

Version 2 replaces the previous-day-close event definition with a rolling three-hour event definition.

### Frozen default event definition

A candidate is the earliest minute on a UTC day where:

```text
later one-minute high >= lowest eligible prior one-minute low × 1.50
```

The baseline minute must precede the crossing minute. The baseline-minute-open gap is capped at 179 minutes, so the exact low trade and exact crossing trade can still be proven to occur within 180 minutes even in the worst case inside the two bars.

Consequences:

- the move may begin on the previous UTC day;
- the price only needs to touch +50%;
- the price does not need to close or remain above +50%;
- same-minute low-to-high moves are conservatively excluded because one-minute bars alone cannot prove ordering;
- the app records only the earliest qualifying event for a pair on each UTC day.

The scanner resolves both the baseline low and threshold crossing to exact Binance aggregate trades. An event cannot qualify as saleable if either exact trade cannot be resolved or the exact elapsed time exceeds three hours.

## Saleability definition

The price does **not** need to remain at the +50% threshold.

A candidate passes saleability when, during the default five minutes after the exact crossing trade:

```text
seller-initiated executed quote notional at any price >= 500 quote units
```

For Binance aggregate trades, `buyer_was_maker = true` means the seller crossed the spread. The app records:

- total seller-initiated notional at any price;
- seller-initiated notional still at or above the threshold;
- first seller-side execution time;
- time and trade price when cumulative seller-side turnover reaches the minimum;
- executable VWAP for the first 500 quote units of seller-side turnover;
- VWAP percentage relative to the threshold;
- lowest and highest seller-side execution prices in the confirmation window;
- truncation and exact-trade-resolution flags.

This is executed-liquidity evidence, not reconstructed historical order-book depth or a guarantee that a hypothetical order would receive identical fills.

## Coin universe

The default canonical quote preference is:

```text
USDT → USDC → FDUSD
```

One currently `TRADING`, Spot-enabled, limit-order-capable pair is selected per base coin. First listing days are eligible even when no previous daily bar exists.

“Tradeable” is Binance exchange-level status. It does not prove availability to a particular UK account, jurisdiction or Binance entity.

## Two-stage workflow

### Stage 1 — 60-day discovery census

1. Store the current Binance Spot universe.
2. Select one canonical pair per base coin.
3. Download 61 daily bars for efficient candidate-day prefiltering.
4. Include first listing days and possible cross-midnight three-hour moves.
5. Fetch minute bars only for shortlisted pair-days, including a three-hour lead-in.
6. Detect the earliest conservatively ordered +50% rolling move.
7. Resolve the exact baseline-low and crossing trades.
8. Verify the exact elapsed time is no more than 10,800 seconds.
9. Measure seller-side executed liquidity at any price after crossing.
10. Count only saleability-passing events in the primary result.

The dashboard provides two event exports:

- **saleable events** — primary result;
- **all candidates** — audit set including exact-trade or saleability failures.

### Stage 2 — look-ahead-safe pre-event datasets

For saleability-passing events, the research collector can obtain:

- ten prior complete UTC days of official archives;
- one-minute and optional one-second bars;
- optional aggregate trades;
- optional raw trades;
- event-day rows strictly before the crossing minute;
- source URLs, hashes, warnings and manifests;
- a compact event manifest and job-level research index.

Large files are uploaded separately to private Supabase Storage and removed from the Render worker immediately. Interrupted jobs are requeued and completed event files are reused.

## Important limitations

- The initial historical universe has survivorship bias because it starts from today’s listed pairs.
- One earliest event per pair-day is retained; later separate surges on the same pair-day are not counted.
- One-minute event detection excludes same-minute low-to-high moves.
- Executed seller-side turnover does not reconstruct order-book depth, latency, queue position or hypothetical market impact.
- The chosen quote pair affects the event; this is not a consolidated coin price.

## Repository structure

```text
app/
  binance.py
  classifier.py
  scanner.py
  research.py
  supabase.py
  web.py
  worker.py
  templates/
supabase/schema.sql
supabase/migrate_v1_to_v2.sql
render.yaml
ANDROID_UPDATE.md
DEPLOYMENT.md
TROUBLESHOOTING.md
docs/DATA_CONTRACT.md
QUALITY_REPORT.md
tests/
```

## Local validation

```bash
pip install -r requirements.txt pytest pyyaml
pytest -q
python -m compileall app
pip check
```
