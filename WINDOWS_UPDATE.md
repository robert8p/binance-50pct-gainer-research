# Simple upgrade to V11 — 25% within eight hours

## What changes

The positive outcome is now a saleable Binance Spot coin rising at least **25%** from the selected local-low baseline within eight hours. It does not need to remain 25% higher.

This is a new event population. Do not reuse the prior 50% scan, controls, export packages or discovered rules as validation evidence.

## 1. Update GitHub

1. Extract `binance_8h_25pct_chatgpt_research_exporter_v11_0_0.zip`.
2. Open the existing GitHub repository.
3. Select **Add file → Upload files**.
4. Upload everything from inside the extracted folder, replacing matching files.
5. Commit with:

```text
Upgrade to v11 saleable 25 percent research
```

No Supabase migration is required.

## 2. Redeploy

Wait for the web service and worker to redeploy. Open:

```text
https://YOUR-APP.onrender.com/health
```

Expected:

```json
{"status":"ok","version":"11.0.0"}
```

## 3. Run a new scan

Queue the fixed 2026 scan shown on the dashboard:

```text
Start inclusive:       2026-01-01
End exclusive:         2026-07-25
Rise threshold:        25%
Rolling window:        8 hours
Minimum saleability:   500 quote units
Saleability window:    300 seconds
```

The old 50% scan will not appear in the V11 export dropdown.

## 4. Run the neutral export

After the new scan completes, select it in Step 2 and queue one export. Download:

- `CHATGPT_25PCT_RESEARCH_INDEX.zip`
- `DISCOVERY_2026_25PCT_UNIVERSE_REFERENCE.zip`
- every `DISCOVERY_2026_25PCT_SYMBOLS_PART_*.zip`

Upload each numbered part separately if required by the 512 MB upload limit.
