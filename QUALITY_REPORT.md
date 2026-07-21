# Quality report — v2.0.0

## Automated validation

The release passes 21 network-free tests covering:

- canonical Spot-pair classification;
- London daylight-saving decision times;
- cross-midnight three-hour moves;
- conservative exclusion of same-minute moves;
- conservative exclusion of a full 180-minute minute-open gap;
- exact baseline and crossing trade resolution;
- saleability below the +50% threshold;
- forced rejection when exact crossing proof is unavailable;
- look-ahead-safe research cutoffs;
- archive timestamp normalization and checksums;
- Supabase modern secret-key handling;
- retried uploads and resumable research bundles;
- additive schema safety.

Additional checks performed:

```text
pytest: 21 passed
Python compilation: passed
Pinned dependency installation: passed
```

## Research-integrity choices

- The +50% move is ordered from an earlier minute to a later minute.
- Exact trades must prove the three-hour interval.
- A later recross cannot replace an unresolved first crossing.
- Saleability is measured at any post-crossing price, so price persistence is not silently required.
- The primary export contains only saleability-passing events; rejected candidates remain auditable.

## Remaining limitations

Live Binance, Supabase and Render calls are not executed by the offline test suite. The first production scan should therefore be followed by inspection of candidate-quality fields and a one-event research collection.
