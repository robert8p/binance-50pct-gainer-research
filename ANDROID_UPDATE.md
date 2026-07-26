# Simple Windows bug-fix update — V10.2.1

## What this fixes

The full-universe export reached 470/470 symbols, then failed while creating the BTC/ETH/BNB reference package with:

```text
cannot insert symbol, already exists
```

The cached reference data already contained a `symbol` column. V10.2 tried to insert a second one. V10.2.1 reuses the existing column.

No research definition, event selection, control selection, or raw market data changes.

## 1. Keep the failed job as an audit record

Do not delete the failed job. It will not restart automatically because its status is already `failed`.

## 2. Update GitHub

1. Extract `binance_chatgpt_research_exporter_full_universe_v10_2_1.zip`.
2. Open the existing GitHub repository.
3. Select **Add file → Upload files**.
4. Upload everything from inside the extracted folder, replacing matching files.
5. Commit with:

```text
Fix V10.2 reference package export
```

No Supabase migration is required.

## 3. Redeploy

Wait for both Render services to redeploy. If the worker is suspended, resume it after the new deployment is available.

Open:

```text
https://YOUR-APP.onrender.com/health
```

Expected:

```json
{"status":"ok","version":"10.2.1"}
```

## 4. Queue one new export

Use the same completed 2026 scan. Do not rerun the scan.

The persistent Render disk should retain the downloaded Binance archive cache, so the rerun should avoid most network downloads. It must still rebuild the data frames and packages.

## 5. Download after completion

Download and upload to ChatGPT:

- `CHATGPT_RESEARCH_INDEX.zip`
- `DISCOVERY_2026_UNIVERSE_REFERENCE.zip`
- every `DISCOVERY_2026_SYMBOLS_PART_*.zip`
