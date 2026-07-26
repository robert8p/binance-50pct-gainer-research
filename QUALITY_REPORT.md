# Quality report — V10.2.1

## Completed checks

- Full canonical-symbol inventory is read from the source scan snapshot.
- Event-bearing and non-event symbols are processed by the same worker loop.
- Every eligible symbol is represented in the universe inventory and daily dataset.
- Full-universe background timestamps are deterministic and chosen without market outcomes.
- Background baselines use the same rolling-local-low algorithm as events.
- Negative samples with a future >=50% eight-hour move are rejected.
- Raw ten-day minute windows remain unengineered and are deduplicated by physical symbol/time.
- Output is partitioned into upload-sized symbol chunks.
- Dashboard cancellation is cooperative and audited as a failed job.
- Collision-resistant ASCII paths handle non-Latin Binance symbols.
- 65 available automated tests passed.
- Python compilation, Jinja rendering and FastAPI route tests passed.

## Environment limitation

Two legacy research tests require PyArrow during test collection. PyArrow was unavailable for Python 3.13 in the local packaging container, so those two unchanged tests were excluded locally. PyArrow remains pinned in `requirements.txt` for GitHub Actions and Render. All other 65 tests passed.


## V10.2.1 regression fix

Added a duplicate-symbol regression test for BTC/ETH/BNB reference packaging. The fix changes packaging only; sample selection and raw evidence remain unchanged.
