# V12 troubleshooting

## How to tell whether the job is progressing

The dashboard shows two stages:

1. **Symbols** — one-minute history is scanned for frozen E1/E2 signal transitions.
2. **Exact executions** — aggregate-trade paths are downloaded for the selected signals.

The worker heartbeat should continue updating. During a large Binance archive download, a counter can remain unchanged for several minutes even though the worker is active.

## Safe restart and resume

V12 writes per-symbol and per-execution checkpoints to the Render persistent disk. If the worker restarts, the job is automatically requeued and resumes from those checkpoints rather than repeating completed work.

Do not delete the Render disk or change `TEMP_DATA_DIR` while the job is running.

## Cancel properly

Press **Cancel** on the dashboard. The worker checks job status between symbols and between exact executions, then stops cooperatively. Do not immediately queue another job until the previous row shows `failed`.

## Worker heartbeat is stale

1. Open Render worker logs.
2. Confirm the worker service is running, not suspended.
3. Confirm the persistent disk is mounted at `/var/data`.
4. Confirm the environment variable `TEMP_DATA_DIR=/var/data`.
5. Restart the worker once. V12 should resume from checkpoints.

## Supabase table error

Run `supabase/migrate_v10_to_v12.sql` once in Supabase SQL Editor, then redeploy both services.

## Out of memory or timeout

Keep the worker on the existing paid plan used for the large 2026 export. The app clears each symbol's archive cache after processing to bound disk usage, but active aggregate-trade files can still require substantial memory.
