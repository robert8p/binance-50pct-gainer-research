# Simple Windows upgrade to V10.1 — 2026 discovery

## 1. Extract the ZIP

Download `binance_chatgpt_research_exporter_2026_v10_1_0.zip`, right-click it and select **Extract All**.

## 2. Supabase

If you already deployed V10, skip this step: V10.1 needs no new database tables.

If upgrading directly from V9 or earlier, run `supabase\migrate_v9_to_v10.sql` in Supabase SQL Editor.

## 3. Update GitHub

1. Open the existing GitHub repository.
2. Select **Add file → Upload files**.
3. Drag everything from inside the extracted V10.1 folder onto GitHub.
4. Replace matching files.
5. Commit with: `Upgrade to v10.1 2026 ChatGPT discovery`.

## 4. Confirm Render

Wait for both services to redeploy. Open:

`https://YOUR-APP.onrender.com/health`

Expected:

`{"status":"ok","version":"10.1.0"}`

## 5. Run the 2026 scan

Leave the fixed dates as:

- Start: `2026-01-01`
- End exclusive: `2026-07-25`

This includes completed UTC data through 24 July 2026. Select **Queue fresh scan** and wait for completion.

## 6. Build the neutral package

Select the completed 2026 scan and select **Queue neutral research export**. The export may take several hours. Do not queue it twice.

## 7. Download and upload to ChatGPT

- `CHATGPT_RESEARCH_INDEX.zip`
- `DISCOVERY_2026_UPLOAD_TO_CHATGPT.zip`

There are deliberately no 2026 validation or sealed files. Those will be collected from separate periods after ChatGPT freezes candidate rules.
