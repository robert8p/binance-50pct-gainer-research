# Troubleshooting — V10.2

## The denominator still equals only event-bearing symbols

Confirm `/health` reports `10.2.1`. If it reports an older version, redeploy both Render services.

## Stop an export

Use the dashboard **Cancel** button. The current symbol operation may finish before the worker notices cancellation.

For an old release without the button:

1. Suspend the Render worker.
2. Run:

```sql
update binance_chatgpt_export_jobs
set status='failed', completed_at=now(), heartbeat_at=null,
    error_message='Cancelled manually'
where status in ('queued','running');
```

3. Deploy V10.2 before resuming the worker.

## Some symbols are daily-only

The universe-reference package intentionally lists every canonical symbol. A recently listed coin may lack ten complete days of minute history and therefore have no raw background window. Its daily data and failure reason remain in the audit files.

## Several discovery ZIPs appear

This is expected. V10.2 chunks compressed symbol evidence at approximately 300 MB per ZIP so the files are practical to upload and analyse.

## Job is slow

The exporter now reads every canonical symbol rather than only event-bearing symbols. Check that the worker heartbeat and symbol count continue advancing. Do not queue a duplicate job.
