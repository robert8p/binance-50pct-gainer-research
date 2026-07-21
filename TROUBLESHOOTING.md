# Troubleshooting — v3.0.0

## Dashboard fails immediately after the upgrade

Run `supabase/migrate_v2_to_v3.sql` in the existing Supabase project's SQL Editor. The v3 dashboard queries the new matched-control job and file tables.

## Matched-control job stays queued

Open the Render background worker and confirm:

- status is **Live**;
- logs contain `Worker started; interrupted jobs recovered`;
- `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are populated;
- the worker is not already processing a scan or another long-running job.

The dashboard does not auto-refresh. Reload it manually.

## Control progress is slow

The first job must obtain roughly 70 days of one-minute archives for every event symbol plus BTC, ETH and BNB. Verified files are cached on the Render persistent disk, so retries and later jobs should be faster.

Do not queue a duplicate job while one is running.

## Fewer controls than requested

Open `matched_control_index.zip` and inspect `quality_report.json` and `control_match_manifest.csv`.

Common reasons include:

- a newly listed coin lacks ten prior days;
- several events for the same coin contaminate much of a short split;
- missing one-minute archives;
- insufficient five-minute executed quote volume;
- another 50% crossing occurs near the proposed control.

A shortfall is preferable to filling the dataset with weak cross-coin controls.

## Job completes with warnings

Warnings can mean:

- not every event received the requested number of controls;
- an event lacked the minimum pre-entry volume at one or more horizons;
- source history was incomplete;
- a symbol failed to download or parse.

The positive event remains in the package and its quality fields disclose the issue.

## Which ZIP should be shared first?

Share `matched_control_index.zip` first. It contains design and quality information but no split feature matrices.

Then use:

1. discovery;
2. validation only after candidate rules are fixed;
3. sealed test only after final preregistration.

## Candidates exist but Saleable is zero

Download **all candidates** and inspect exact-trade and seller-side turnover fields. A coin can touch +50% and fail because the exact crossing cannot be proved or because insufficient seller-initiated turnover occurred afterwards.

## Health is live but no worker heartbeat appears

Check the Render worker logs and verify both services use the same Supabase URL and server-side secret key.
