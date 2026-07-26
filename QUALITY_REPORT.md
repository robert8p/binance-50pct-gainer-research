# Quality report — V11.0.0

## Research-integrity changes

- Positive label is frozen at a saleable >=25% rise within 480 minutes.
- Event and negative baselines use the same rolling local-low algorithm.
- Same-coin controls and universe backgrounds are rejected if they rise 25% within eight hours.
- Old 50% scans are excluded by a distinct event-definition version.
- Package names are distinct from the 50% research exports.
- The app generates no predictive features and selects no trading rule.

## Operational checks

- Full canonical-universe inventory retained.
- Ten-day minute history remains deduplicated by symbol and timestamp.
- Symbol ZIPs remain chunked around 300 MB, below the 512 MB upload limit.
- Non-Latin symbol paths remain collision-resistant.
- Dashboard cancellation retained.

## Expected scaling

The 25% threshold will generate more events, controls and package parts than the 50% threshold. Longer runtime and greater storage use are expected and are not, by themselves, failures.
