# Deployment — V10.2

1. Cancel the V10.1 export and suspend the Render worker.
2. Replace the repository files with V10.2.
3. No database migration is required from V10.0/V10.1.
4. Resume the worker and wait for both services to redeploy.
5. Confirm `/health` returns version `10.2.1`.
6. Reuse the completed `2026-01-01` to `2026-07-25` scan.
7. Queue one neutral export.
8. The progress denominator must now equal the full canonical symbol universe.
9. Download the index, universe-reference ZIP and every numbered symbol ZIP.
