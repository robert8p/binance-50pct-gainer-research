# Troubleshooting — v5.0.0

## Dashboard fails immediately after upgrade

Run `supabase/migrate_v4_to_v5.sql`. The v5 dashboard queries the new baseline-context tables.

## Baseline-context job remains queued

Open the Render worker logs. Confirm the worker is Live and both Supabase variables are populated. Restart the worker; queued jobs are preserved.

## Fresh staged job fails immediately

Fresh staged mode requires:

- an explicit historical scan whose exclusive end date is no later than `2026-05-22`;
- matched controls built with `180` included in the decision horizons.

Recreate the matched-control job if its contamination-before value is only 120 minutes.

## Job completes with contaminated-control warnings

A control experienced an accidental 50% sequential low-to-later-high move between its pseudo-baseline and control anchor, or had incomplete data across that interval. The app flags it rather than silently treating it as a valid negative example.

## Job has insufficient-history warnings

The offset ten days before baseline also calculates up to ten days of preceding features. A new listing may therefore need about 20 days of prior history and can legitimately fail completeness checks. Do not impute missing minutes.

## Job is slow

V5 can require roughly 20 days of history before the earliest baseline and processes eleven snapshots per sample. The persistent cache makes subsequent runs faster. Do not queue duplicate jobs.

## Which files should be shared?

For the existing dataset:

```text
baseline_context_index.zip
baseline_context_exploratory.zip
```

For fresh staged evidence, share the index and discovery package first. Keep validation and sealed test unopened.
