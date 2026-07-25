# Simple Windows upgrade to V10

## 1. Extract the V10 ZIP

Download `binance_chatgpt_research_exporter_v10_0_0.zip`, right-click it and select **Extract All**.

## 2. Update Supabase

1. Open the extracted folder.
2. Open `supabase\migrate_v9_to_v10.sql` in Notepad.
3. Press `Ctrl+A`, then `Ctrl+C`.
4. Open your existing Supabase project.
5. Open **SQL Editor → New query**.
6. Paste the SQL and select **Run**.

This adds the neutral export job, file and issue tables. It does not delete earlier data.

## 3. Update GitHub

1. Open the existing GitHub repository.
2. Select **Add file → Upload files**.
3. Drag everything from inside the extracted V10 folder onto GitHub.
4. Replace matching files.
5. Commit with:

`Upgrade to v10 ChatGPT research exporter`

## 4. Confirm Render

Wait for the web service and worker to redeploy. Open:

`https://YOUR-APP.onrender.com/health`

Expected result:

`{"status":"ok","version":"10.0.0"}`

## 5. Run the fresh scan

On the dashboard, leave the fixed dates as:

- Start: `2025-01-01`
- End exclusive: `2025-06-30`

Select **Queue fresh scan** and wait until it completes.

## 6. Build the neutral packages

Select the completed 2025-01-01 to 2025-06-30 scan and select **Queue neutral research export**.

The export can be large and may take several hours. Do not queue it twice.

## 7. Download only these first

- `CHATGPT_RESEARCH_INDEX.zip`
- `DISCOVERY_UPLOAD_TO_CHATGPT.zip`

Upload both to ChatGPT.

Do not open or upload:

- `VALIDATION_DO_NOT_OPEN.zip`
- `SEALED_TEST_DO_NOT_OPEN.zip`

until ChatGPT has frozen the candidate patterns and test criteria.
