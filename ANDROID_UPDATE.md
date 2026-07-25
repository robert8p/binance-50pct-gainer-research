# Simple Windows update — V10.2

## 1. Stop the old export

1. Open Render and suspend `binance-50pct-scanner-worker`.
2. In Supabase SQL Editor run:

```sql
update binance_chatgpt_export_jobs
set status = 'failed',
    completed_at = now(),
    heartbeat_at = null,
    error_message = 'Cancelled manually: superseded by full-universe exporter'
where status in ('queued','running');
```

Leave the worker suspended until V10.2 is deployed.

## 2. Update GitHub

1. Extract `binance_chatgpt_research_exporter_full_universe_v10_2_0.zip`.
2. Open the existing GitHub repository.
3. Select **Add file → Upload files**.
4. Upload everything from inside the extracted folder, replacing matching files.
5. Commit with:

```text
Upgrade to v10.2 full-universe ChatGPT exporter
```

No new Supabase migration is required if V10 is already installed.

## 3. Redeploy

Resume the Render worker after GitHub has updated. Wait for both services to redeploy.

Open:

```text
https://YOUR-APP.onrender.com/health
```

Expected:

```json
{"status":"ok","version":"10.2.0"}
```

## 4. Queue the corrected export

Use the already completed 2026 scan. You do not need to rerun it.

The job's total-symbol count should now represent the complete canonical Binance universe, not only event-bearing coins.

The dashboard now includes a **Cancel** button for queued or running export jobs.

## 5. Download after completion

Download and upload to ChatGPT:

- `CHATGPT_RESEARCH_INDEX.zip`
- `DISCOVERY_2026_UNIVERSE_REFERENCE.zip`
- every `DISCOVERY_2026_SYMBOLS_PART_*.zip`
