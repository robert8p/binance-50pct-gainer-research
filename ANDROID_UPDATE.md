# Android update from v1.x to v2.0.0

These steps assume the existing local repository is:

```text
~/binance-50pct-app
```

and the new ZIP is in Android Downloads.

## 1. Replace the local files

In Termux:

```bash
cd ~/binance-50pct-app
unzip -o ~/storage/downloads/binance_3h_50pct_surge_research_v2_0_0.zip
```

This overwrites application files but does not delete the local `.git` directory.

## 2. Configure Git identity if the first commit has not succeeded

```bash
git config --global user.name "Rob"
git config --global user.email "YOUR_GITHUB_EMAIL"
```

## 3. Commit and push

When the GitHub repository does not yet exist:

```bash
git add .
git commit -m "Deploy Binance 3-hour 50 percent surge app v2"
git branch -M main
gh repo create binance-50pct-gainer-research --private --source=. --remote=origin --push
```

When the repository already exists and `origin` is configured:

```bash
git add .
git commit -m "Upgrade to rolling 3-hour surge scanner v2"
git push origin main
```

## 4. Apply the Supabase migration

For an existing v1 database, open `supabase/migrate_v1_to_v2.sql` in GitHub, select the raw view and copy the entire file. For a database that has not yet been created, use the full `supabase/schema.sql` instead.

In Supabase:

1. Open **SQL Editor**.
2. Create a new query.
3. Paste the selected SQL file.
4. Select **Run**.

The script is additive and preserves v1 records.

## 5. Redeploy Render

If the Blueprint already exists, GitHub push normally triggers redeployment. In Render, confirm both services finish deploying.

If not yet created, create the Blueprint from `render.yaml` and supply the same three secrets documented in `DEPLOYMENT.md`.

## 6. Verify

Open:

```text
https://YOUR-RENDER-WEB-URL/health
```

Expected:

```json
{"status":"ok","version":"2.0.0"}
```

Then queue a 60-day scan. Do not reuse a v1 scan for v2 research; v1 scans are deliberately hidden from the v2 research selector because the event definition has changed.
